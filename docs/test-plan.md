# {octicon}`checklist` Test plans

A *test plan* is a declarative list of CLI invocations and the results each one should produce. Click Extra runs the plan against any command or binary as separate subprocesses, checking exit codes and output. It is the black-box, subprocess-level complement to [`CliRunner`](testing.md), which drives a CLI in-process: a test plan never imports the target, so it works just as well against a compiled binary, a shell command, or a CLI written in another language.

```{important}
Parsing a plan from YAML needs the optional `pyyaml` dependency. Install it with the `yaml` extra:

​```{code-block} shell-session
$ pip install click-extra[yaml]
​```

The engine itself (building `CLITestCase` objects and running them) has no such requirement: only `parse_test_plan` does.
```

## Writing a plan

A plan is a YAML list. Each entry is one case: the parameters to append to the command, plus the expectations to check. A case with no expectation only asserts that the command ran.

```{code-block} yaml
- cli_parameters: --version
  exit_code: 0

- cli_parameters: forecast --city paris
  stdout_contains: Sunny
  timeout: 5

- cli_parameters: --help
  stdout_regex_matches:
    - Usage:.+
  skip_platforms:
    - windows
```

The directives map one-to-one onto {class}`~click_extra.test_plan.CLITestCase` fields:

- `cli_parameters`: arguments appended to the command (a string is split, a list is used as-is).
- `exit_code`: the expected process exit code.
- `stdout_contains` / `stderr_contains`: substrings that must appear.
- `stdout_regex_matches` / `stderr_regex_matches`: regexes that must each match somewhere.
- `stdout_regex_fullmatch` / `stderr_regex_fullmatch`: a regex that must fully match, line by line.
- `strip_ansi`: strip ANSI escapes before matching.
- `timeout`: seconds before the case fails as a timeout.
- `skip_platforms` / `only_platforms`: [`extra_platforms`](https://kdeldycke.github.io/extra-platforms) identifiers (`linux`, `macos`, `windows`, group IDs) controlling where the case runs.

## Running from the command line

The `click-extra test-plan` subcommand runs a plan against a target. Point it at a command on the `PATH`, a command line, or a path to a binary:

```{code-block} shell-session
$ click-extra test-plan --command weather --plan-file plan.yaml
Running 3 test cases across 7 workers (os.cpu_count()=8).
Test plan results - Total: 3, Skipped: 0, Failed: 0
```

Cases run in parallel by default, one fewer than the available logical CPUs (see [`--jobs`](execution.md#parallel-jobs)). Pass `--jobs max` to use every core, or `--jobs 1` for sequential execution, which lets `--exit-on-error` stop on the first failure. With no `--plan-file` or `--plan-envvar`, a built-in default plan exercises `--version` and `--help`. On an interactive terminal a spinner reports progress; it is silent in pipes and CI logs, and `--no-progress` turns it off.

## Running from Python

{func}`~click_extra.test_plan.parse_test_plan` turns YAML into cases, and {func}`~click_extra.test_plan.run_test_plan` runs them, returning a {class}`~collections.Counter` of `total`, `skipped`, and `failed`:

```{code-block} python
from click_extra import parse_test_plan, run_test_plan

cases = list(parse_test_plan(open("plan.yaml").read()))
counter = run_test_plan("weather", cases, jobs=4)
if counter["failed"]:
    raise SystemExit(1)
```

Build cases directly when a plan is computed rather than read from YAML (this path needs no `yaml` extra):

```{code-block} python
from click_extra import CLITestCase, run_test_plan

cases = [
    CLITestCase(cli_parameters="--version", exit_code=0),
    CLITestCase(cli_parameters="forecast --city lyon", stdout_contains="Cloudy"),
]
run_test_plan("weather", cases)
```

## `click_extra.test_plan` API

```{eval-rst}
.. autoclasstree:: click_extra.test_plan
   :strict:

.. automodule:: click_extra.test_plan
   :members:
   :undoc-members:
   :show-inheritance:
```
