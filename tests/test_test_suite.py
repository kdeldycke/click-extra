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

"""Tests for the declarative CLI test-suite engine and its ``test-suite`` command.

Covers three surfaces:

- :func:`~click_extra.test_suite.parse_test_suite` and the
  :class:`~click_extra.test_suite.CLITestCase` normalization it feeds.
- :func:`~click_extra.test_suite.run_test_suite`, the parallel orchestrator.
- The ``click-extra test-suite`` subcommand wiring it to the CLI.

The host Python interpreter stands in for the command under test, so cases stay
fast and platform-neutral.
"""

from __future__ import annotations

import sys

import pytest

from click_extra import (
    DEFAULT_TEST_SUITE,
    CLITestCase,
    ConfigFormat,
    cases_from_data,
    load_test_suite,
    parse_test_suite,
    run_test_suite,
)
from click_extra.cli import demo

# A case that passes: the interpreter exits 0 on --version.
PASS_CASE = CLITestCase(cli_parameters="--version", exit_code=0)
# A case that fails: --version never exits 99, so the expectation mismatches.
FAIL_CASE = CLITestCase(cli_parameters="--version", exit_code=99)

# --- parse_test_suite ---------------------------------------------------------


def test_parse_returns_cases():
    """A well-formed YAML suite yields one CLITestCase per entry."""
    cases = list(
        parse_test_suite(
            "- cli_parameters: --version\n  exit_code: 0\n- cli_parameters: --help\n",
        )
    )
    assert len(cases) == 2
    assert all(isinstance(c, CLITestCase) for c in cases)
    assert cases[0].exit_code == 0


@pytest.mark.parametrize(
    ("suite_string", "fmt"),
    (
        (
            '[[cases]]\ncli_parameters = "--version"\nexit_code = 0\n\n'
            '[[cases]]\ncli_parameters = "--help"\n',
            ConfigFormat.TOML,
        ),
        (
            '[{"cli_parameters": "--version", "exit_code": 0}, '
            '{"cli_parameters": "--help"}]',
            ConfigFormat.JSON,
        ),
    ),
)
def test_parse_returns_cases_per_format(suite_string, fmt):
    """TOML (cases under [[cases]]) and JSON (bare array) yield the same cases."""
    cases = list(parse_test_suite(suite_string, fmt))
    assert len(cases) == 2
    assert all(isinstance(c, CLITestCase) for c in cases)
    assert cases[0].exit_code == 0


def test_parse_toml_requires_cases_key():
    """A TOML mapping without a top-level 'cases' array of tables is rejected."""
    with pytest.raises(ValueError, match="cases"):
        list(parse_test_suite('title = "weather"\n', ConfigFormat.TOML))


def test_parse_rejects_non_suite_format():
    """A format that cannot represent a list of cases is rejected."""
    with pytest.raises(ValueError, match="cannot express a test suite"):
        list(parse_test_suite("[]", ConfigFormat.INI))


@pytest.mark.parametrize(
    ("suite", "exception"),
    (
        ("", ValueError),
        (None, ValueError),
        ("[]", ValueError),
        ("key: value", ValueError),
        ("- not-a-real-directive: 1", ValueError),
    ),
)
def test_parse_rejects_malformed(suite, exception):
    """Empty, mapping-without-cases, and unknown-directive suites raise."""
    with pytest.raises(exception):
        list(parse_test_suite(suite))


# --- load_test_suite ----------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "content"),
    (
        ("suite.yaml", "- cli_parameters: --version\n  exit_code: 0\n"),
        ("suite.yml", "- cli_parameters: --version\n  exit_code: 0\n"),
        ("suite.toml", '[[cases]]\ncli_parameters = "--version"\nexit_code = 0\n'),
        ("suite.json", '[{"cli_parameters": "--version", "exit_code": 0}]'),
    ),
)
def test_load_detects_format_from_extension(tmp_path, filename, content):
    """The file extension selects the parser, so each format yields the case."""
    path = tmp_path / filename
    path.write_text(content)
    cases = list(load_test_suite(path))
    assert len(cases) == 1
    assert cases[0].exit_code == 0


def test_load_rejects_unknown_extension(tmp_path):
    """An extension matching no suite format is rejected."""
    path = tmp_path / "suite.txt"
    path.write_text("- cli_parameters: --version\n")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        list(load_test_suite(path))


# --- cases_from_data ---------------------------------------------------------


def test_cases_from_data_builds_cases():
    """A list of directive mappings becomes CLITestCase instances."""
    cases = list(
        cases_from_data([
            {"cli_parameters": "--version", "exit_code": 0},
            {"cli_parameters": "--help"},
        ])
    )
    assert len(cases) == 2
    assert all(isinstance(c, CLITestCase) for c in cases)
    assert cases[0].exit_code == 0


def test_cases_from_data_rejects_unknown_directive():
    """An unknown directive in a mapping is rejected."""
    with pytest.raises(ValueError, match="invalid directives"):
        list(cases_from_data([{"not_a_real_directive": 1}]))


# --- CLITestCase normalization -----------------------------------------------


def test_case_normalizes_scalars():
    """String scalars are coerced: exit_code to int, cli_parameters to a tuple."""
    case = CLITestCase(cli_parameters="--foo bar", exit_code="7")
    assert case.exit_code == 7
    assert case.cli_parameters == ("--foo", "bar")


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (5, 5.0),
        (5.0, 5.0),
        ("5", 5.0),
        (None, None),
    ),
)
def test_case_normalizes_timeout(value, expected):
    """A timeout given as int, float, or numeric string becomes a float.

    Plain integers are what every config format produces for a bare number, so
    they must be accepted (a `timeout: 5` in any suite).
    """
    assert CLITestCase(timeout=value).timeout == expected


@pytest.mark.parametrize("value", (True, [5]))
def test_case_rejects_non_numeric_timeout(value):
    """A boolean or non-scalar timeout is rejected as not-a-float."""
    with pytest.raises(ValueError, match="timeout is not a float"):
        CLITestCase(timeout=value)


# --- output_* combined-stream directives -------------------------------------

# An unbuffered (-u) script that interleaves stdout and stderr in a known order,
# so the merged stream is deterministic: "out-1", "err-1", "out-2".
_INTERLEAVE = (
    "-u",
    "-c",
    "import sys; sys.stdout.write('out-1\\n'); "
    "sys.stderr.write('err-1\\n'); sys.stdout.write('out-2\\n')",
)


def test_output_contains_sees_merged_stream():
    """output_contains matches substrings from both stdout and stderr."""
    case = CLITestCase(
        cli_parameters=_INTERLEAVE,
        output_contains=("out-1", "err-1", "out-2"),
    )
    # No exception means every substring was found in the merged stream.
    case.run_cli_test(sys.executable, None, None)


def test_output_regex_preserves_cross_stream_order():
    """output_regex_matches sees stdout and stderr interleaved in write order."""
    case = CLITestCase(
        cli_parameters=_INTERLEAVE,
        # out-1 (stdout), err-1 (stderr), out-2 (stdout): only the merged stream
        # carries all three in this order. stdout alone lacks err-1.
        output_regex_matches=(r"out-1.*err-1.*out-2",),
    )
    case.run_cli_test(sys.executable, None, None)


def test_output_directive_mismatch_fails():
    """A substring absent from the merged stream fails the case."""
    case = CLITestCase(cli_parameters=_INTERLEAVE, output_contains=("absent",))
    with pytest.raises(AssertionError):
        case.run_cli_test(sys.executable, None, None)


def test_non_utf8_output_does_not_crash_the_harness():
    """Bytes that are not valid UTF-8 are escaped, not a reader-thread crash.

    A binary emitting its platform's legacy encoding (cp1252 on Windows) used
    to kill the capture with a bare UnicodeDecodeError, surfacing as a
    "got 'NoneType'" case failure with no hint of the cause. The escaped bytes
    now flow into the captured stream where assertions can see them.
    """
    case = CLITestCase(
        cli_parameters=(
            "-c",
            # 0x82 is not valid UTF-8: written raw, bypassing text encoding.
            r"import sys; sys.stdout.buffer.write(b'caf\x82-end\n')",
        ),
        exit_code=0,
        stdout_contains=("-end",),
    )
    case.run_cli_test(sys.executable, None, None)


def test_child_inherits_utf8_io_encoding():
    """The subprocess emits UTF-8 regardless of the platform's default.

    PYTHONIOENCODING is injected into the child environment so CPython-based
    binaries write UTF-8 on piped stdout, where Windows would pick cp1252 and
    desynchronize from the harness's UTF-8 decoding.
    """
    case = CLITestCase(
        cli_parameters=("-c", "import sys; print(sys.stdout.encoding.lower())"),
        exit_code=0,
        stdout_contains=("utf",),
    )
    case.run_cli_test(sys.executable, None, None)


def test_output_and_stream_directives_are_mutually_exclusive():
    """Combining output_* with stdout_*/stderr_* is rejected at construction."""
    with pytest.raises(ValueError, match="cannot be mixed"):
        CLITestCase(output_contains="x", stdout_contains="y")


# --- run_test_suite -----------------------------------------------------------


@pytest.mark.parametrize("jobs", (1, 2, 3))
def test_run_counts_pass_and_fail(jobs):
    """Pass/fail tallies match regardless of the worker count."""
    counter = run_test_suite(
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
    counter = run_test_suite(
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
    counter = run_test_suite(
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
    run_test_suite(
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
    run_test_suite(
        sys.executable,
        [PASS_CASE],
        stats=False,
        show_progress=False,
    )
    out = capsys.readouterr().out
    assert "Test suite results" not in out
    assert "os.cpu_count()" not in out


# --- click-extra test-suite subcommand ----------------------------------------


def test_cli_runs_default_suite(invoke):
    """With no suite source, the subcommand runs the built-in default suite."""
    result = invoke(demo, ["test-suite", "--command", sys.executable])
    assert result.exit_code == 0
    assert f"Total: {len(DEFAULT_TEST_SUITE)}" in result.output


def test_cli_runs_suite_file(invoke, tmp_path):
    """A --suite-file is parsed and run against the target command."""
    suite = tmp_path / "suite.yaml"
    suite.write_text("- cli_parameters: --version\n  exit_code: 0\n")
    result = invoke(
        demo,
        ["test-suite", "--command", sys.executable, "--suite-file", str(suite)],
    )
    assert result.exit_code == 0
    assert "Total: 1" in result.output
    assert "Failed: 0" in result.output


def test_cli_runs_toml_suite_file(invoke, tmp_path):
    """A TOML --suite-file runs without the yaml extra, since TOML is built in."""
    suite = tmp_path / "suite.toml"
    suite.write_text('[[cases]]\ncli_parameters = "--version"\nexit_code = 0\n')
    result = invoke(
        demo,
        ["test-suite", "--command", sys.executable, "--suite-file", str(suite)],
    )
    assert result.exit_code == 0
    assert "Total: 1" in result.output
    assert "Failed: 0" in result.output


def test_cli_reports_failure_exit_code(invoke, tmp_path):
    """A failing case makes the subcommand exit non-zero."""
    suite = tmp_path / "suite.yaml"
    suite.write_text("- cli_parameters: --version\n  exit_code: 99\n")
    result = invoke(
        demo,
        ["test-suite", "--command", sys.executable, "--suite-file", str(suite)],
    )
    assert result.exit_code == 1
    assert "Failed: 1" in result.output


def test_cli_rejects_non_integer_jobs(invoke):
    """--jobs is click-extra's JobsOption, so a non-numeric value is refused."""
    result = invoke(
        demo, ["test-suite", "--command", sys.executable, "--jobs", "banana"]
    )
    assert result.exit_code == 2
    assert "banana" in result.stderr


def test_cli_requires_command(invoke):
    """Without --command/--binary, the subcommand errors with a usage message."""
    result = invoke(demo, ["test-suite"])
    assert result.exit_code == 2
    assert "Missing option '--command' / '--binary'" in result.stderr


def test_cli_resolves_suite_from_config(invoke, tmp_path, monkeypatch):
    """With no --suite-file, the suite comes from [tool.click-extra.test-suite]."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.click-extra.test-suite]\nfile = "configured.yaml"\n',
        encoding="UTF-8",
    )
    (tmp_path / "configured.yaml").write_text(
        "- cli_parameters: --version\n  exit_code: 0\n",
        encoding="UTF-8",
    )
    monkeypatch.chdir(tmp_path)

    result = invoke(demo, ["test-suite", "--command", sys.executable])
    assert result.exit_code == 0
    # The configured suite has 1 case; the built-in default has 3, so Total: 1
    # proves the [tool.click-extra.test-suite] file was read.
    assert "Total: 1" in result.output


def test_cli_resolves_native_cases_from_config(invoke, tmp_path, monkeypatch):
    """Cases can be declared natively under [[tool.click-extra.test-suite.cases]]."""
    (tmp_path / "pyproject.toml").write_text(
        "[[tool.click-extra.test-suite.cases]]\n"
        'cli_parameters = "--version"\n'
        "exit_code = 0\n\n"
        "[[tool.click-extra.test-suite.cases]]\n"
        'cli_parameters = "--help"\n'
        "exit_code = 0\n",
        encoding="UTF-8",
    )
    monkeypatch.chdir(tmp_path)

    result = invoke(demo, ["test-suite", "--command", sys.executable])
    assert result.exit_code == 0
    # The two native [[...cases]] entries run (not the 3-case built-in default).
    assert "Total: 2" in result.output
    assert "Failed: 0" in result.output
