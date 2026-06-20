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

"""Tests for the declarative CLI test-plan engine and its ``test-plan`` command.

Covers three surfaces:

- :func:`~click_extra.test_plan.parse_test_plan` and the
  :class:`~click_extra.test_plan.CLITestCase` normalization it feeds.
- :func:`~click_extra.test_plan.run_test_plan`, the parallel orchestrator.
- The ``click-extra test-plan`` subcommand wiring it to the CLI.

The host Python interpreter stands in for the command under test, so cases stay
fast and platform-neutral.
"""

from __future__ import annotations

import sys

import pytest

from click_extra import (
    DEFAULT_TEST_PLAN,
    CLITestCase,
    parse_test_plan,
    run_test_plan,
)
from click_extra.cli import demo

# A case that passes: the interpreter exits 0 on --version.
PASS_CASE = CLITestCase(cli_parameters="--version", exit_code=0)
# A case that fails: --version never exits 99, so the expectation mismatches.
FAIL_CASE = CLITestCase(cli_parameters="--version", exit_code=99)

# --- parse_test_plan ---------------------------------------------------------


def test_parse_returns_cases():
    """A well-formed YAML plan yields one CLITestCase per entry."""
    cases = list(
        parse_test_plan(
            "- cli_parameters: --version\n  exit_code: 0\n- cli_parameters: --help\n",
        )
    )
    assert len(cases) == 2
    assert all(isinstance(c, CLITestCase) for c in cases)
    assert cases[0].exit_code == 0


@pytest.mark.parametrize(
    ("plan", "exception"),
    (
        ("", ValueError),
        (None, ValueError),
        ("[]", ValueError),
        ("key: value", TypeError),
        ("- not-a-real-directive: 1", ValueError),
    ),
)
def test_parse_rejects_malformed(plan, exception):
    """Empty, non-list, and unknown-directive plans raise."""
    with pytest.raises(exception):
        list(parse_test_plan(plan))


# --- CLITestCase normalization -----------------------------------------------


def test_case_normalizes_scalars():
    """String scalars are coerced: exit_code to int, cli_parameters to a tuple."""
    case = CLITestCase(cli_parameters="--foo bar", exit_code="7")
    assert case.exit_code == 7
    assert case.cli_parameters == ("--foo", "bar")


# --- run_test_plan -----------------------------------------------------------


@pytest.mark.parametrize("jobs", (1, 2, 3))
def test_run_counts_pass_and_fail(jobs):
    """Pass/fail tallies match regardless of the worker count."""
    counter = run_test_plan(
        sys.executable,
        [PASS_CASE, FAIL_CASE, PASS_CASE],
        jobs=jobs,
        stats=False,
        show_progress=False,
    )
    assert counter["total"] == 3
    assert counter["failed"] == 1
    assert counter["skipped"] == 0


def test_run_select_test_skips_others():
    """select_test runs only the chosen 1-based cases; the rest count as skipped."""
    counter = run_test_plan(
        sys.executable,
        [PASS_CASE, FAIL_CASE, PASS_CASE],
        select_test=(1, 3),
        stats=False,
        show_progress=False,
    )
    assert counter["failed"] == 0
    assert counter["skipped"] == 1


def test_run_exit_on_error_bails_sequentially():
    """With one worker, exit_on_error stops before later cases run."""
    counter = run_test_plan(
        sys.executable,
        [FAIL_CASE, PASS_CASE, PASS_CASE],
        jobs=1,
        exit_on_error=True,
        stats=False,
        show_progress=False,
    )
    # The run bailed after the first (failing) case: the two trailing passes
    # never ran, so they are neither passed nor skipped.
    assert counter["failed"] == 1


def test_run_stats_echoes_summary(capsys):
    """stats prints the worker line up front and the result tally at the end."""
    run_test_plan(
        sys.executable,
        [PASS_CASE, PASS_CASE],
        jobs=2,
        stats=True,
        show_progress=False,
    )
    out = capsys.readouterr().out
    assert "Running 2 test cases across 2 workers" in out
    assert "os.cpu_count()=" in out
    assert "Total: 2" in out
    assert "Failed: 0" in out


def test_run_no_stats_is_quiet(capsys):
    """Without stats, neither the worker line nor the tally is printed."""
    run_test_plan(
        sys.executable,
        [PASS_CASE],
        stats=False,
        show_progress=False,
    )
    out = capsys.readouterr().out
    assert "Test plan results" not in out
    assert "os.cpu_count()" not in out


# --- click-extra test-plan subcommand ----------------------------------------


def test_cli_runs_default_plan(invoke):
    """With no plan source, the subcommand runs the built-in default plan."""
    result = invoke(demo, ["test-plan", "--command", sys.executable])
    assert result.exit_code == 0
    assert f"Total: {len(DEFAULT_TEST_PLAN)}" in result.output


def test_cli_runs_plan_file(invoke, tmp_path):
    """A --plan-file is parsed and run against the target command."""
    plan = tmp_path / "plan.yaml"
    plan.write_text("- cli_parameters: --version\n  exit_code: 0\n")
    result = invoke(
        demo,
        ["test-plan", "--command", sys.executable, "--plan-file", str(plan)],
    )
    assert result.exit_code == 0
    assert "Total: 1" in result.output
    assert "Failed: 0" in result.output


def test_cli_reports_failure_exit_code(invoke, tmp_path):
    """A failing case makes the subcommand exit non-zero."""
    plan = tmp_path / "plan.yaml"
    plan.write_text("- cli_parameters: --version\n  exit_code: 99\n")
    result = invoke(
        demo,
        ["test-plan", "--command", sys.executable, "--plan-file", str(plan)],
    )
    assert result.exit_code == 1
    assert "Failed: 1" in result.output


def test_cli_rejects_non_integer_jobs(invoke):
    """--jobs is click-extra's JobsOption, so a non-numeric value is refused."""
    result = invoke(
        demo, ["test-plan", "--command", sys.executable, "--jobs", "banana"]
    )
    assert result.exit_code == 2
    assert "banana" in result.stderr


def test_cli_resolves_plan_from_config(invoke, tmp_path, monkeypatch):
    """With no --plan-file, the plan comes from [tool.click-extra.test-plan]."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.click-extra.test-plan]\nfile = "configured.yaml"\n',
        encoding="UTF-8",
    )
    (tmp_path / "configured.yaml").write_text(
        "- cli_parameters: --version\n  exit_code: 0\n",
        encoding="UTF-8",
    )
    monkeypatch.chdir(tmp_path)

    result = invoke(demo, ["test-plan", "--command", sys.executable])
    assert result.exit_code == 0
    # The configured plan has 1 case; the built-in default has 3, so Total: 1
    # proves the [tool.click-extra.test-plan] file was read.
    assert "Total: 1" in result.output
