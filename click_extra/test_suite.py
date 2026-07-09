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

"""Declarative, black-box CLI test suites.

A test suite is a list of :class:`CLITestCase` invocations: each runs a target
command (a name, a command line, or a path to a binary) once with extra
parameters, then checks its exit code and ``stdout``/``stderr`` against literal,
substring, or regex expectations. Cases carry their own platform skip/only
rules, so one suite runs across operating systems unchanged.

Suites are written in any list-capable configuration format and loaded with
:func:`load_test_suite` (which picks the format from the file extension) or
:func:`parse_test_suite` (which parses a serialized string). TOML and JSON are
built in; YAML and the other :data:`~click_extra.test_suite.SUITE_FORMATS` need their matching
``click-extra[…]`` extra. :func:`run_test_suite` drives a list of cases against
a target, parallelized per the resolved ``--jobs`` count (see
:func:`click_extra.execution.run_jobs`) and reporting live progress through a
:class:`click_extra.spinner.Spinner`.

This is the black-box, subprocess-level complement to
:class:`click_extra.testing.CliRunner`, which drives a CLI in-process.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, fields
from pathlib import Path
from shutil import which
from subprocess import PIPE, STDOUT, TimeoutExpired, run

from boltons.iterutils import flatten
from boltons.strutils import strip_ansi
from extra_platforms import current_platform, extract_members, is_windows

from . import echo
from .config.formats import (
    ConfigFormat,
    disabled_format_message,
    parse_content,
    read_file,
)
from .execution import run_jobs
from .spinner import Spinner
from .testing import (
    STREAM_FIELDS,
    StreamView,
    args_cleanup,
    regex_fullmatch_line_by_line,
    render_cli_run,
)

SUITE_FORMATS: tuple[ConfigFormat, ...] = (
    # Built-in, no extra dependency.
    ConfigFormat.TOML,
    ConfigFormat.JSON,
    # Each needs its matching click-extra[…] extra.
    ConfigFormat.YAML,
    ConfigFormat.JSON5,
    ConfigFormat.JSONC,
    ConfigFormat.HJSON,
)
"""Configuration formats a test suite can be serialized in, built-in ones first.

These are the formats able to represent a top-level list of case mappings,
matched against a file's extension by :func:`load_test_suite`. TOML and JSON
parse with no extra dependency; the others each need their matching
``click-extra[…]`` extra. TOML has no bare top-level array, so a TOML suite
lists its cases under a ``[[cases]]`` array of tables (see
:func:`parse_test_suite`); the others use a bare list. INI (no nesting) and XML
(no natural list representation) are excluded.

Per-format availability is resolved by
:class:`~click_extra.config.formats.ConfigFormat`, so a format whose parser is
not installed raises an :exc:`ImportError` pointing at its extra at parse time.
"""

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator
    from typing import Any

    from extra_platforms._types import _TNestedReferences


class SkippedTest(Exception):
    """Raised when a test case should be skipped."""


def _split_args(cli: str) -> list[str]:
    """Split a command-line string into a list of arguments.

    ```{todo}
    Tokenize Windows command lines with quoting/escaping support, like `shlex`
    does on POSIX. The current `str.split()` fallback only splits on whitespace,
    so a quoted argument such as `--name "two words"` is wrongly broken into
    three tokens. Use [w32lex](https://github.com/maxpat78/w32lex), the Windows
    counterpart to `shlex`.
    ```
    """
    if is_windows():
        return cli.split()
    # For Unix platforms, we have the dedicated shlex module.
    else:
        return shlex.split(cli)


@dataclass(order=True)
class CLITestCase:
    """A single CLI test case: how to invoke the command and what to expect.

    Each case runs the command-under-test once with `cli_parameters` appended,
    then checks the captured result against the expectation directives below. A
    case with no expectation only asserts the command ran (plus `exit_code`, if
    set).
    """

    cli_parameters: tuple[str, ...] | str = field(default_factory=tuple)
    """Arguments and options appended to the command-under-test.

    A plain string is split into arguments (on spaces on Windows, with `shlex`
    elsewhere); a list or tuple is used as-is.
    """

    skip_platforms: _TNestedReferences = field(default_factory=tuple)
    """Platforms (or platform-group IDs) on which to skip this case.

    Accepts `extra_platforms` identifiers such as `linux`, `macos`, `windows`,
    in any case, mixed freely with group IDs.
    """

    only_platforms: _TNestedReferences = field(default_factory=tuple)
    """Restrict this case to these platforms; skip it everywhere else.

    The mirror image of `skip_platforms`, using the same identifiers.
    """

    timeout: float | str | None = None
    """Seconds before the command is killed and the case fails as a timeout.

    Falls back to the command's `--timeout` default, then to no limit.
    """

    exit_code: int | str | None = None
    """Expected process exit code; the case fails on any other code."""

    strip_ansi: bool = False
    """Strip ANSI escape sequences from the captured output before matching."""

    output_contains: tuple[str, ...] | str = field(default_factory=tuple)
    """Substrings that must all be present in the combined output.

    The combined output interleaves stdout and stderr in the order the command
    wrote them, matching what a user sees in a terminal. The ``output_*``
    directives are mutually exclusive with the ``stdout_*`` / ``stderr_*`` ones:
    a single subprocess run captures either the merged stream or the separate
    ones, not both.
    """

    stdout_contains: tuple[str, ...] | str = field(default_factory=tuple)
    """Substrings that must all be present in stdout."""

    stderr_contains: tuple[str, ...] | str = field(default_factory=tuple)
    """Substrings that must all be present in stderr."""

    output_regex_matches: tuple[re.Pattern | str, ...] | str = field(
        default_factory=tuple
    )
    """Regexes that must each match somewhere in the combined output (searched,
    `re.DOTALL`). See `output_contains` for the merged-stream semantics."""

    stdout_regex_matches: tuple[re.Pattern | str, ...] | str = field(
        default_factory=tuple
    )
    """Regexes that must each match somewhere in stdout (searched, `re.DOTALL`)."""

    stderr_regex_matches: tuple[re.Pattern | str, ...] | str = field(
        default_factory=tuple
    )
    """Regexes that must each match somewhere in stderr (searched, `re.DOTALL`)."""

    output_regex_fullmatch: re.Pattern | str | None = None
    """Regex that must fully match the combined output, line by line. See
    `output_contains` for the merged-stream semantics."""

    stdout_regex_fullmatch: re.Pattern | str | None = None
    """Regex that must fully match stdout, line by line."""

    stderr_regex_fullmatch: re.Pattern | str | None = None
    """Regex that must fully match stderr, line by line."""

    execution_trace: str | None = None
    """Rendering of the command execution and its output.

    Populated after the case runs, for inspection on failure; not a directive
    you set in a test suite.
    """

    @property
    def has_merged_output_directives(self) -> bool:
        """Whether any ``output_*`` directive (merged stream) is set."""
        return any(
            getattr(self, f.name) for f in fields(self) if f.name.startswith("output_")
        )

    @property
    def has_separate_stream_directives(self) -> bool:
        """Whether any ``stdout_*`` or ``stderr_*`` directive (separate streams) is
        set."""
        return any(
            getattr(self, f.name)
            for f in fields(self)
            if f.name.startswith(("stdout_", "stderr_"))
        )

    def __post_init__(self) -> None:
        """Normalize all fields.

        ```{note}
        We iterate with `fields()` + `getattr()` instead of `asdict()`
        because `asdict()` deep-copies field values via `copy.deepcopy()`,
        which fails on Python < 3.13 for `MappingProxyType` objects (used
        internally by `extra_platforms`).
        ```
        """
        for f in fields(self):
            field_id = f.name
            field_data = getattr(self, field_id)
            # Validates and normalize integer properties.
            if field_id == "exit_code":
                if isinstance(field_data, str):
                    field_data = int(field_data)
                elif field_data is not None and not isinstance(field_data, int):
                    raise ValueError(f"exit_code is not an integer: {field_data}")

            # Validates and normalize float properties.
            elif field_id == "timeout":
                # A numeric string or an int is coerced to float; bool is an int
                # subclass but not a valid duration, so it is rejected below.
                if (
                    isinstance(field_data, str)
                    or isinstance(field_data, int)
                    and not isinstance(field_data, bool)
                ):
                    field_data = float(field_data)
                elif field_data is not None and not isinstance(field_data, float):
                    raise ValueError(f"timeout is not a float: {field_data}")
                # Timeout can only be unset or positive.
                if field_data and field_data < 0:
                    raise ValueError(f"timeout is negative: {field_data}")

            # Validates and normalize boolean properties.
            elif field_id == "strip_ansi":
                if not isinstance(field_data, bool):
                    raise ValueError(f"strip_ansi is not a boolean: {field_data}")

            # Validates and normalize tuple of strings.
            else:
                if field_data:
                    # Wraps single string and other types into a tuple.
                    if isinstance(field_data, str) or not isinstance(
                        field_data, Sequence
                    ):
                        # CLI parameters provided as a long string needs to be split so
                        # that each argument is a separate item in the final tuple.
                        if field_id == "cli_parameters":
                            field_data = _split_args(field_data)
                        else:
                            field_data = (field_data,)

                    for item in field_data:
                        if not isinstance(item, str):
                            raise TypeError(f"Invalid string in {field_id}: {item}")
                    # Ignore blank value.
                    field_data = tuple(i for i in field_data if i.strip())

            # Normalize any mishmash of platform and group IDs into a set of platforms.
            if field_id.endswith("_platforms") and field_data:
                field_data = frozenset(extract_members(field_data))

            # Validates fields containing one or more regexes.
            if "_regex_" in field_id and field_data:
                # Compile all regexes.
                valid_regexes = []
                for regex in flatten((field_data,)):
                    try:
                        # Let dots in regex match newlines.
                        valid_regexes.append(re.compile(regex, re.DOTALL))
                    except re.error as ex:
                        raise ValueError(
                            f"Invalid regex in {field_id}: {regex}"
                        ) from ex
                # Normalize single regex to a single element.
                if field_id.endswith("_fullmatch"):
                    if valid_regexes:
                        field_data = valid_regexes.pop()
                    else:
                        field_data = None
                else:
                    field_data = tuple(valid_regexes)

            setattr(self, field_id, field_data)

        # output_* (merged stream) and stdout_*/stderr_* (separate streams)
        # require different subprocess captures, so a case picks one family.
        if self.has_merged_output_directives and self.has_separate_stream_directives:
            raise ValueError(
                "output_* directives (merged stream) cannot be mixed with "
                "stdout_*/stderr_* directives (separate streams) in the same "
                "test case: a subprocess run captures one or the other."
            )

    def run_cli_test(
        self,
        command: Path | str,
        additional_skip_platforms: _TNestedReferences | None,
        default_timeout: float | None,
    ) -> None:
        """Run a CLI command and check its output against the test case.

        The provided `command` can be either:

        - a path to a binary or script to execute;
        - a command name to be searched in the `PATH`,
        - a command line with arguments to be parsed and executed by the shell.

        ```{todo}
        Add support for environment variables.
        ```
        """
        if self.only_platforms and current_platform() not in self.only_platforms:  # type: ignore[operator]
            required = ", ".join(
                sorted(trait.id for trait in extract_members(self.only_platforms))
            )
            raise SkippedTest(f"Test case only runs on platforms: {required}")

        if current_platform() in extract_members(
            self.skip_platforms, additional_skip_platforms
        ):
            raise SkippedTest(f"Skipping test case on platform: {current_platform()}")

        if self.timeout is None and default_timeout is not None:
            logging.info(f"Set default test case timeout to {default_timeout} seconds")
            self.timeout = default_timeout

        # Separate the command into binary file path and arguments.
        args = []
        if isinstance(command, str):
            args = _split_args(command)
            command = args[0]
            args = args[1:]
            # Ensure the command to execute is in PATH.
            if not which(command):
                raise FileNotFoundError(f"Command not found in PATH: {command!r}")
            # Resolve the command to an absolute path.
            command = which(command)  # type: ignore[assignment]
            assert command is not None

        # Check the binary exists and is executable.
        binary = Path(command).resolve()
        assert binary.exists()
        assert binary.is_file()
        assert os.access(binary, os.X_OK)

        clean_args = args_cleanup(binary, args, self.cli_parameters)
        logging.info(f"Run CLI command: {' '.join(clean_args)}")

        # When the case asserts on the merged stream (output_* directives), route
        # stderr into stdout so the OS interleaves both in write order: result.stdout
        # then holds the combined stream and result.stderr is None. Otherwise capture
        # the two streams separately.
        try:
            result = run(
                clean_args,
                stdout=PIPE,
                stderr=STDOUT if self.has_merged_output_directives else PIPE,
                timeout=self.timeout,  # type: ignore[arg-type]
                check=False,
                # Force UTF-8 decoding of subprocess output. The encoding parameter
                # only affects parent-side decoding and does not change child process
                # behavior. Without this, Windows defaults to cp1252, causing
                # UnicodeDecodeError on non-ASCII output (like contributor names).
                encoding="utf-8",
                # The child-side half of the same contract: a CPython-based binary
                # (including Nuitka builds) honors PYTHONIOENCODING and emits UTF-8
                # on piped stdout, where Windows would default to cp1252. An
                # explicitly exported PYTHONIOENCODING wins over ours.
                env={"PYTHONIOENCODING": "utf8", **os.environ},
                # Last-resort guard for binaries that emit non-UTF-8 bytes anyway:
                # escape them instead of raising UnicodeDecodeError from the reader
                # thread, which surfaced as a bare "expected string or bytes-like
                # object, got 'NoneType'" case failure with no hint of the cause.
                # Escaped bytes show up visibly in the assertion diff instead.
                errors="backslashreplace",
            )
        except TimeoutExpired:
            raise TimeoutError(
                f"CLI timed out after {self.timeout} seconds: {' '.join(clean_args)}"
            )

        # Normalize the subprocess result so the assertion loop reads the same shape
        # the renderer does: the merged stream lands in view.output, the separate
        # streams in view.stdout/view.stderr.
        view = StreamView.from_completed_process(result)

        # Execution has been completed, save the output for user's inspection.
        self.execution_trace = render_cli_run(clean_args, result)
        for line in self.execution_trace.splitlines():
            logging.info(line)

        for f in fields(self):
            field_id = f.name
            field_data = getattr(self, field_id)
            if field_id == "exit_code":
                if field_data is not None:
                    logging.info(f"Test exit code, expecting: {field_data}")
                    if result.returncode != field_data:
                        raise AssertionError(
                            f"CLI exited with code {result.returncode}, "
                            f"expected {field_data}"
                        )
                # The specific exit code matches, let's proceed to the next test.
                continue

            # Ignore non-output fields, and empty test cases.
            elif not (
                field_id.startswith(("output_", "stdout_", "stderr_")) and field_data
            ):
                continue

            # Select the stream and its label from the shared field-prefix table.
            output = ""
            name = ""
            for prefix, (label, attr) in STREAM_FIELDS.items():
                if field_id.startswith(prefix):
                    output = getattr(view, attr)
                    name = label
                    break

            if self.strip_ansi:
                logging.info(f"Strip ANSI sequences from {name}")
                output = strip_ansi(output)

            if field_id.endswith("_contains"):
                for sub_string in field_data:
                    logging.info(f"Check if {name} contains {sub_string!r}")
                    if sub_string not in output:
                        raise AssertionError(
                            f"{name} does not contain {sub_string!r}\n"
                            f"  Actual {name}: {output!r}"
                        )

            elif field_id.endswith("_regex_matches"):
                for regex in field_data:
                    logging.info(f"Check if {name} matches {regex!r}")
                    if not regex.search(output):
                        raise AssertionError(
                            f"{name} does not match regex {regex}\n"
                            f"  Actual {name}: {output!r}"
                        )

            elif field_id.endswith("_regex_fullmatch"):
                regex_fullmatch_line_by_line(field_data, output)


DEFAULT_TEST_SUITE: list[CLITestCase] = [
    # Output the version of the CLI.
    CLITestCase(cli_parameters="--version"),
    # Test combination of version and verbosity.
    CLITestCase(cli_parameters=("--verbosity", "DEBUG", "--version")),
    # Test help output.
    CLITestCase(cli_parameters="--help"),
]


def cases_from_data(data: Any) -> Generator[CLITestCase, None, None]:
    """Build :class:`CLITestCase` instances from already-parsed suite data.

    The in-memory counterpart to :func:`parse_test_suite` (which parses a string)
    and :func:`load_test_suite` (which reads a file): feed it a suite that is
    already a Python object, such as the native ``cases`` mappings declared in a
    ``[tool.<cli>.test-suite]`` config section.

    A suite is a list of case mappings, each keyed by ``CLITestCase`` directive
    names. Formats with no bare top-level array (TOML) carry that list under a
    top-level ``cases`` key, so a mapping is unwrapped here.

    :raises ValueError: the suite is empty, a mapping suite omits ``cases``, or a
        case uses unknown directives.
    :raises TypeError: the suite is not a list, or a case is not a mapping.
    """
    if isinstance(data, dict):
        if "cases" not in data:
            raise ValueError(
                "A mapping-style test suite must list its cases under a top-level "
                "'cases' key (the [[cases]] array of tables in TOML)."
            )
        suite = data["cases"]
    else:
        suite = data

    if not suite:
        raise ValueError("Empty test suite")
    if not isinstance(suite, list):
        raise TypeError(f"Test suite is not a list: {suite}")

    directives = frozenset(CLITestCase.__dataclass_fields__.keys())

    for index, test_case in enumerate(suite):
        if not isinstance(test_case, dict):
            raise TypeError(f"Test case #{index + 1} is not a dict: {test_case}")
        if not directives.issuperset(test_case):
            raise ValueError(
                f"Test case #{index + 1} contains invalid directives: "
                f"{set(test_case) - directives}"
            )
        yield CLITestCase(**test_case)


def parse_test_suite(
    suite_string: str | None,
    fmt: ConfigFormat = ConfigFormat.YAML,
) -> Generator[CLITestCase, None, None]:
    """Parse a serialized test suite string into :class:`CLITestCase` instances.

    ``fmt`` selects the serialization format, one of
    :data:`~click_extra.test_suite.SUITE_FORMATS`; it defaults to YAML for string
    sources with no extension to key on, such as an environment variable.
    :func:`load_test_suite` is the file-based counterpart.

    :raises ValueError: the suite is empty, ``fmt`` cannot express a suite, a
        mapping suite omits ``cases``, or a case uses unknown directives.
    :raises TypeError: the suite is not a list, or a case is not a mapping.
    :raises ImportError: the format's optional parser is not installed.
    """
    if not suite_string:
        raise ValueError("Empty test suite")

    if fmt not in SUITE_FORMATS:
        raise ValueError(
            f"{fmt} cannot express a test suite; use one of: "
            + ", ".join(map(str, SUITE_FORMATS))
        )

    if not fmt.enabled:
        raise ImportError(disabled_format_message(fmt))

    yield from cases_from_data(parse_content(fmt, suite_string))


def load_test_suite(path: Path) -> Generator[CLITestCase, None, None]:
    """Read a test suite file and parse it by the format of its extension.

    The format is resolved from ``path``'s name over the list-capable
    :data:`~click_extra.test_suite.SUITE_FORMATS` (so ``suite.toml`` parses as TOML,
    ``suite.yaml`` as YAML). Reading and format detection are delegated to
    :func:`click_extra.config.formats.read_file`.

    :raises ValueError: the file extension matches no suite format.
    :raises ImportError: the matched format's optional parser is not installed.
    """
    yield from cases_from_data(read_file(path, SUITE_FORMATS))


def run_test_suite(
    command: Path | str,
    cases: Sequence[CLITestCase],
    *,
    jobs: int = 1,
    select_test: Sequence[int] | None = None,
    skip_platform: _TNestedReferences | None = None,
    timeout: float | None = None,
    exit_on_error: bool = False,
    show_trace_on_error: bool = True,
    stats: bool = True,
    show_progress: bool = True,
) -> Counter:
    """Run a list of test cases against a target command and tally the results.

    Cases are parallelized per ``jobs`` (see
    :func:`click_extra.execution.run_jobs`): at one worker they run sequentially
    and lazily, so ``exit_on_error`` can stop before the rest start; otherwise
    they run in a thread pool and every case runs to completion. Either way
    outcomes are tallied in submission order. On an interactive terminal a
    :class:`click_extra.spinner.Spinner` reports progress unless ``show_progress``
    is false.

    :param command: The target to test: a command name, a command line, or a
        path to a binary or script.
    :param cases: The test cases to run.
    :param jobs: Number of parallel workers; ``1`` runs sequentially.
    :param select_test: 1-based case numbers to run; others are skipped.
    :param skip_platform: Extra platforms (or group IDs) to skip every case on.
    :param timeout: Default per-case timeout in seconds when a case sets none.
    :param exit_on_error: Stop at the first failure (sequential runs only).
    :param show_trace_on_error: Echo the execution trace of each failed case.
    :param stats: Echo a one-line worker summary up front and a result tally.
    :param show_progress: Allow the progress spinner on an interactive terminal.
    :return: A :class:`collections.Counter` with ``total``, ``skipped``, and
        ``failed`` keys. A non-zero ``failed`` count signals the caller to exit
        with an error.
    """
    counter = Counter(total=len(cases), skipped=0, failed=0)

    # Select the cases to run (respecting select_test), keeping their 1-based
    # numbers for stable reporting.
    pending: list[tuple[int, CLITestCase]] = []
    for index, test_case in enumerate(cases):
        test_number = index + 1
        if select_test and test_number not in select_test:
            logging.warning(f"Test #{test_number} skipped by user request.")
            counter["skipped"] += 1
            continue
        pending.append((test_number, test_case))

    def run_case(item: tuple[int, CLITestCase]) -> tuple[int, str, CLITestCase]:
        """Run one case, returning its number, outcome, and the case itself."""
        test_number, test_case = item
        logging.info(f"Run test #{test_number}...")
        try:
            logging.debug(f"Test case parameters: {test_case}")
            test_case.run_cli_test(
                command,
                additional_skip_platforms=skip_platform,
                default_timeout=timeout,
            )
        except SkippedTest as ex:
            logging.warning(f"Test #{test_number} skipped: {ex}")
            return test_number, "skipped", test_case
        except Exception as ex:  # noqa: BLE001
            logging.error(f"Test #{test_number} failed: {ex}")
            return test_number, "failed", test_case
        return test_number, "passed", test_case

    def tally(outcome: tuple[int, str, CLITestCase]) -> None:
        """Record an outcome in the counters and echo a failure's trace."""
        _, status, test_case = outcome
        if status == "skipped":
            counter["skipped"] += 1
        elif status == "failed":
            counter["failed"] += 1
            if show_trace_on_error and test_case.execution_trace:
                echo(test_case.execution_trace)

    # Surface the parallelism picture up front so logs make clear whether cases
    # run concurrently, and how that maps to the host's logical CPU count.
    # os.cpu_count() reports logical CPUs (hardware threads), which is what the
    # --jobs option keys on: on a 2-core host `auto` resolves to 1 (sequential).
    if stats:
        echo(
            f"Running {len(pending)} test cases across {jobs} workers "
            f"(os.cpu_count()={os.cpu_count()})."
        )

    # An indeterminate spinner reports live progress on an interactive terminal.
    # It stays silent off a TTY, so pipes and CI logs are unaffected. Traces and
    # the summary print only after it stops, so they never collide with a frame.
    completed = 0

    def progress_label() -> str:
        return f"Running test cases ({completed}/{len(pending)})"

    spinner = Spinner(progress_label(), enabled=None if show_progress else False)
    outcomes: list[tuple[int, str, CLITestCase]] = []
    bailed = False
    # run_jobs drives the cases per the worker count: sequential and lazy at one
    # worker (so exit_on_error stops before the rest start), thread-pooled
    # otherwise, yielding in submission order so traces and counters stay
    # ordered. subprocess.run releases the GIL, so workers overlap each case's
    # process spawn and execution.
    is_sequential = jobs <= 1 or len(pending) <= 1
    with spinner:
        for outcome in run_jobs(run_case, pending, jobs=jobs):
            completed += 1
            spinner.label = progress_label()
            outcomes.append(outcome)
            # exit_on_error only short-circuits when sequential; in parallel
            # every case is already in flight, so the run completes.
            if is_sequential and outcome[1] == "failed" and exit_on_error:
                logging.debug("Don't continue testing, a failed test was found.")
                bailed = True
                break

    # The spinner has stopped and cleared its line: record outcomes and echo any
    # failure traces now, clear of the animation.
    for outcome in outcomes:
        tally(outcome)

    # A bail-out skips the summary; the caller still sees the non-zero count.
    if stats and not bailed:
        echo(
            "Test suite results - "
            + ", ".join(f"{k.title()}: {v}" for k, v in counter.items())
        )

    return counter
