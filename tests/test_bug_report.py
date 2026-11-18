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

import errno
import json
import logging
import re
from pathlib import Path

import click
import pytest

from click_extra import (
    VersionOption,
    argument,
    command,
    compact_frames,
    culprit_function,
    describe_error,
    echo,
    group,
    jobs_option,
    log_report,
    option,
)
from click_extra.bug_report import (
    MAX_FRAMES,
    MAX_MESSAGE_LENGTH,
    REPORT_END,
    REPORT_START,
    option_words,
    report_form_url,
)

REPORT_URL = "https://github.com/orchard/harvest/issues/new?template=bug.yml"


def report_block(stderr: str) -> list[str]:
    """The lines between the two markers of the one report in `stderr`."""
    lines = stderr.splitlines()
    return lines[lines.index(REPORT_START) + 1 : lines.index(REPORT_END)]


def test_unexpected_error_ends_with_a_report(invoke, tmp_path):
    """An error of a command with a `report_url` ends the run with a bug report.

    The report links to the form with a title, and masks paths and arguments.
    """

    @command(report_url=REPORT_URL)
    @option("--basket", type=click.Path())
    @option("--fruit")
    @argument("orchards", nargs=-1)
    def harvest(basket, fruit, orchards):
        """Share the fruits among the baskets."""
        raise ZeroDivisionError("no basket to share the plums with")

    basket = str(tmp_path / "basket")
    result = invoke(harvest, "--basket", basket, "--fruit", "plum", "north", "south")

    assert result.exit_code == 1
    assert "harvest stopped on this error, which is a bug." in result.stderr
    assert report_form_url(REPORT_URL, "ZeroDivisionError in harvest") in result.stderr
    block = report_block(result.stderr)
    assert block[0].startswith("harvest")
    assert block[1] == "Options: --basket <path> --fruit plum <orchards> <orchards>"
    assert block[3] == "ZeroDivisionError: no basket to share the plums with"
    # The frames start at the callback: the ones Click runs it with are left out.
    (frame,) = block[4:]
    assert re.fullmatch(
        rf"  {re.escape(__name__)}:\d+ in "
        r"test_unexpected_error_ends_with_a_report\.<locals>\.harvest",
        frame,
    )
    assert basket not in "\n".join(block)
    assert "Traceback (most recent call last)" in result.stderr


def test_report_is_saved_in_the_cache(invoke):
    """The report is saved in a file of the cache, whose path ends the output."""

    @command(report_url=REPORT_URL)
    def harvest():
        raise KeyError("plum")

    result = invoke(harvest)

    assert result.exit_code == 1
    *_, intro, last = result.stderr.splitlines()
    assert intro == "This report is also saved in this file:"
    saved = Path(last).read_text(encoding="UTF-8")
    assert saved.startswith("harvest stopped on this error, which is a bug.\n")
    assert report_block(saved) == report_block(result.stderr)
    assert last not in saved


def test_no_report_without_url(invoke):
    """A command without a `report_url` lets the error through, as Click does."""

    @command
    def harvest():
        raise ZeroDivisionError

    result = invoke(harvest)

    assert result.exit_code == 1
    assert isinstance(result.exception, ZeroDivisionError)
    assert REPORT_START not in result.stderr


def test_os_error_ends_with_one_line(invoke):
    """An `OSError` is for the user to fix: it gets a one-line error, not a report."""

    @command(report_url=REPORT_URL)
    def harvest():
        raise PermissionError("the barn is locked")

    result = invoke(harvest)

    assert result.exit_code == 1
    assert "Error: the barn is locked" in result.stderr
    assert REPORT_START not in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    ("error", "exit_code"),
    (
        pytest.param(click.UsageError("too many plums"), 2, id="usage-error"),
        pytest.param(click.exceptions.Exit(3), 3, id="exit"),
        pytest.param(click.Abort(), 1, id="abort"),
        pytest.param(EOFError(), 1, id="end-of-input"),
        pytest.param(BrokenPipeError(errno.EPIPE, "Broken pipe"), 1, id="broken-pipe"),
    ),
)
def test_click_exits_pass_through(invoke, error, exit_code):
    """The exceptions that Click exits with are no bug: the run ends as in Click."""

    @command(report_url=REPORT_URL)
    def harvest():
        raise error

    @command(name="harvest")
    def plain_harvest():
        raise error

    result = invoke(harvest)

    assert result.exit_code == exit_code
    assert REPORT_START not in result.stderr
    assert result.stderr == invoke(plain_harvest).stderr


def test_subcommand_error_reports_once(invoke):
    """The error of a subcommand gets one report, with the options of both levels."""

    @group(report_url=REPORT_URL)
    @option("--season")
    def orchard(season):
        """Tend the orchard."""

    @orchard.command()
    @option("--fruit")
    def pick(fruit):
        """Pick one kind of fruit."""
        raise ZeroDivisionError("no basket")

    result = invoke(orchard, "--season", "autumn", "pick", "--fruit", "plum")

    assert result.exit_code == 1
    assert result.stderr.count(REPORT_START) == 1
    assert report_form_url(REPORT_URL, "ZeroDivisionError in pick") in result.stderr
    assert (
        report_block(result.stderr)[1] == "Options: --season autumn pick --fruit plum"
    )


def test_report_survives_a_missing_version(invoke, monkeypatch):
    """A version that cannot be found leaves the report without it."""

    def no_version(self):
        raise RuntimeError("Cannot find module")

    monkeypatch.setattr(VersionOption, "version", property(no_version))

    @command(report_url=REPORT_URL)
    def harvest():
        raise ZeroDivisionError

    result = invoke(harvest)

    assert result.exit_code == 1
    assert report_block(result.stderr)[0].startswith("harvest, Python ")


def test_report_shows_resolved_jobs(invoke):
    """`--jobs` keeps no value in the context, and shows the count it resolved to."""

    @command(report_url=REPORT_URL)
    @jobs_option
    def harvest():
        raise ZeroDivisionError

    result = invoke(harvest, "--jobs", "2")

    assert result.exit_code == 1
    assert report_block(result.stderr)[1] == "Options: --jobs 2"


def test_log_report_lets_the_run_go_on(invoke):
    """A CLI logs a report of its own for a failure that does not stop the run."""

    @command(report_url=REPORT_URL)
    def harvest():
        log_report(
            logging.WARNING,
            "Two plums were set aside after unexpected errors.",
            "Plums set aside",
            ("", "Plums set aside: 2"),
        )
        echo("Harvest done.")

    result = invoke(harvest)

    assert result.exit_code == 0
    assert "Harvest done." in result.stdout
    assert report_form_url(REPORT_URL, "Plums set aside") in result.stderr
    assert report_block(result.stderr)[-1] == "Plums set aside: 2"


@pytest.mark.parametrize("agent", (True, False))
def test_report_addresses_an_agent(invoke, monkeypatch, agent):
    """An AI agent running the CLI is asked to show the report to its user."""
    monkeypatch.setattr("extra_platforms.is_any_agent", lambda: agent)

    @command(report_url=REPORT_URL)
    def harvest():
        raise ZeroDivisionError

    result = invoke(harvest)

    assert ("AI agent: show this report to your user" in result.stderr) is agent


@pytest.mark.parametrize(
    ("param", "value", "words"),
    (
        (click.Option(["--fruit"]), "plum", ["--fruit", "plum"]),
        (click.Option(["--basket"], type=click.Path()), "b", ["--basket", "<path>"]),
        (click.Option(["--basket"]), Path("b"), ["--basket", "<path>"]),
        (click.Option(["--fruit"]), re.compile("pl.m"), ["--fruit", "<regexp>"]),
        (
            click.Option(["--fruit"], multiple=True),
            ("plum", "fig"),
            ["--fruit", "plum", "--fruit", "fig"],
        ),
        (click.Option(["--size"], nargs=2, type=int), (3, 4), ["--size", "3", "4"]),
        (click.Option(["--ripe/--green"]), True, ["--ripe"]),
        (click.Option(["--ripe/--green"]), False, ["--green"]),
        (click.Option(["--washed"], is_flag=True), False, []),
        (click.Option(["-v", "--verbose"], count=True), 2, ["--verbose", "--verbose"]),
        (
            click.Argument(["orchards"], nargs=-1),
            ("n", "s"),
            ["<orchards>", "<orchards>"],
        ),
        (click.Argument(["basket"], type=click.Path()), "b", ["<path>"]),
    ),
)
def test_option_words(param, value, words):
    """A parameter renders as typed, its paths, patterns and arguments masked."""
    assert option_words(param, value) == words


def test_report_form_url_keeps_the_query():
    """The title joins the query of the URL, like the template of the form."""
    url = report_form_url(REPORT_URL, "KeyError in pick")
    assert url == f"{REPORT_URL}&title=KeyError+in+pick"


@pytest.mark.parametrize(
    ("expt", "described"),
    (
        (ValueError("ripe \n  plum"), "ValueError: ripe plum"),
        (KeyError(), "KeyError"),
        (
            json.JSONDecodeError("Expecting value", "", 0),
            "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
        ),
        (
            ValueError("plum " * MAX_MESSAGE_LENGTH),
            f"ValueError: {('plum ' * MAX_MESSAGE_LENGTH)[:MAX_MESSAGE_LENGTH]}...",
        ),
    ),
)
def test_describe_error(expt, described):
    """An error reads as its class and message, on one line of capped length."""
    assert describe_error(expt) == described


def test_compact_frames_keeps_the_innermost():
    """A deep traceback keeps its innermost frames, and counts the others."""

    def dig(depth):
        if not depth:
            raise ValueError
        dig(depth - 1)

    with pytest.raises(ValueError) as info:
        dig(MAX_FRAMES + 5)

    frames = compact_frames(info.value.__traceback__)
    assert len(frames) == MAX_FRAMES + 1
    assert re.fullmatch(r"\.\.\. \d+ outer frames", frames[0])
    assert frames[-1].endswith(
        " in test_compact_frames_keeps_the_innermost.<locals>.dig"
    )


def test_culprit_function_skips_nameless_code():
    """The innermost function with a name stands for a lambda it calls."""

    def sort_baskets(baskets):
        return sorted(baskets, key=lambda basket: 1 / basket)

    with pytest.raises(ZeroDivisionError) as info:
        sort_baskets([1, 0])

    package = __name__.partition(".")[0]
    assert culprit_function(info.value.__traceback__, package) == "sort_baskets"
    assert culprit_function(info.value.__traceback__, "orchard") == ""
