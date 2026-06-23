# {octicon}`checklist` Test plans

A *test plan* is a declarative list of CLI invocations and the results each one should produce. Click Extra runs the plan against any command or binary as separate subprocesses, checking exit codes and output. It is the black-box, subprocess-level complement to [`CliRunner`](testing.md), which drives a CLI in-process: a test plan never imports the target, so it works just as well against a compiled binary, a shell command, or a CLI written in another language.

```{important}
A plan file's format is taken from its extension. TOML (`.toml`) and JSON (`.json`) work out of the box; YAML (`.yaml`, `.yml`), JSON5, JSONC, and Hjson each need their parser installed. See [extra dependencies](install.md#extra-dependencies) for the optional installs, and the [`--config` formats](config.md#formats) for the full list of formats and extensions.

The engine itself (building `CLITestCase` objects and running them) needs none of these: only parsing a serialized plan does.
```

## Writing a plan

A plan is a list of cases. Each entry is one case: the parameters to append to the command, plus the expectations to check. A case with no expectation only asserts that the command ran.

The same plan is shown below in every supported format. TOML and JSON come first, since they need no extra dependency. TOML has no bare top-level list, so its cases sit under a `[[cases]]` array of tables; every other format is a bare list of case mappings.

`````{tab-set}

````{tab-item} TOML
```{code-block} toml
[[cases]]
cli_parameters = "--version"
exit_code = 0

[[cases]]
cli_parameters = "forecast --city paris"
stdout_contains = "Sunny"
timeout = 5

[[cases]]
cli_parameters = "--help"
stdout_regex_matches = ["Usage:.+"]
skip_platforms = ["windows"]
```
````

````{tab-item} JSON
```{code-block} json
[
  {
    "cli_parameters": "--version",
    "exit_code": 0
  },
  {
    "cli_parameters": "forecast --city paris",
    "stdout_contains": "Sunny",
    "timeout": 5
  },
  {
    "cli_parameters": "--help",
    "stdout_regex_matches": ["Usage:.+"],
    "skip_platforms": ["windows"]
  }
]
```
````

````{tab-item} YAML
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
````

````{tab-item} JSON5
```{code-block} json5
[
  // Print the version and check it exits cleanly.
  {
    cli_parameters: '--version',
    exit_code: 0,
  },
  {
    cli_parameters: 'forecast --city paris',
    stdout_contains: 'Sunny',
    timeout: 5,
  },
  {
    cli_parameters: '--help',
    stdout_regex_matches: ['Usage:.+'],
    skip_platforms: ['windows'],
  },
]
```
````

````{tab-item} JSONC
```{code-block} json5
[
  // Print the version and check it exits cleanly.
  {
    "cli_parameters": "--version",
    "exit_code": 0,
  },
  {
    "cli_parameters": "forecast --city paris",
    "stdout_contains": "Sunny",
    "timeout": 5,
  },
  {
    "cli_parameters": "--help",
    "stdout_regex_matches": ["Usage:.+"],
    "skip_platforms": ["windows"],
  },
]
```
````

````{tab-item} Hjson
```{code-block} text
[
  # Print the version and check it exits cleanly.
  {
    cli_parameters: --version
    exit_code: 0
  }
  {
    cli_parameters: forecast --city paris
    stdout_contains: Sunny
    timeout: 5
  }
  {
    cli_parameters: --help
    stdout_regex_matches: [
      Usage:.+
    ]
    skip_platforms: [
      windows
    ]
  }
]
```
````
`````

The directives map one-to-one onto {class}`~click_extra.test_plan.CLITestCase` fields:

| Directive                                                             | Meaning                                                                                                                                                |
| :-------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `cli_parameters`                                                      | Arguments appended to the command (a string is split, a list is used as-is).                                                                           |
| `exit_code`                                                           | The expected process exit code.                                                                                                                        |
| `stdout_contains` / `stderr_contains`                                 | Substrings that must appear.                                                                                                                           |
| `stdout_regex_matches` / `stderr_regex_matches`                       | Regexes that must each match somewhere.                                                                                                                |
| `stdout_regex_fullmatch` / `stderr_regex_fullmatch`                   | A regex that must fully match, line by line.                                                                                                           |
| `output_contains` / `output_regex_matches` / `output_regex_fullmatch` | The same three checks, but against the combined output (stdout and stderr interleaved in the order the command wrote them, like a terminal).           |
| `strip_ansi`                                                          | Strip ANSI escapes before matching.                                                                                                                    |
| `timeout`                                                             | Seconds before the case fails as a timeout.                                                                                                            |
| `skip_platforms` / `only_platforms`                                   | [`extra_platforms`](https://kdeldycke.github.io/extra-platforms) identifiers (`linux`, `macos`, `windows`, group IDs) controlling where the case runs. |

The `output_*` directives are mutually exclusive with the `stdout_*` / `stderr_*` ones in a single case, since one subprocess run captures either the merged stream or the separate ones. For order-sensitive checks make the command write unbuffered (like `python -u`): a child that block-buffers stdout will have it surface after stderr.

## Running from the command line

The `click-extra test-plan` subcommand runs a plan against a target. Point it at a command on the `PATH`, a command line, or a path to a binary:

```{code-block} shell-session
$ click-extra test-plan --command weather --plan-file plan.yaml
Running 3 test cases across 7 workers (os.cpu_count()=8).
Test plan results - Total: 3, Skipped: 0, Failed: 0
```

Cases run in parallel by default, one fewer than the available logical CPUs (see [`--jobs`](execution.md#parallel-jobs)). Pass `--jobs max` to use every core, or `--jobs 1` for sequential execution, which lets `--exit-on-error` stop on the first failure. On an interactive terminal a spinner reports progress; it is silent in pipes and CI logs, and `--no-progress` turns it off.

### Configuring the plan

Rather than passing `--plan-file` every time, a project can declare its plan once under `[tool.click-extra.test-plan]`, and `click-extra test-plan` picks it up when no plan is given on the command line:

```{code-block} toml
[tool.click-extra.test-plan]
file = "tests/cli-test-plan.yaml"  # default; format taken from the extension
# inline = "- cli_parameters: --version"  # or embed a YAML plan directly
# timeout = 30  # default per-case timeout in seconds
```

The resolution precedence is: `--plan-file`/`--plan-envvar`, then `[tool.click-extra.test-plan]` `inline`, then its `file`, then a built-in default plan that exercises `--version` and `--help`. The config maps onto the {class}`~click_extra.config.builtin.TestPlanConfig` schema (wrapped by {class}`~click_extra.config.builtin.ClickExtraConfig`).

## Running from Python

{func}`~click_extra.test_plan.load_test_plan` reads a plan file, picking the format from its extension (use {func}`~click_extra.test_plan.parse_test_plan` for a plan already held as a string), and {func}`~click_extra.test_plan.run_test_plan` runs the cases, returning a {class}`~collections.Counter` of `total`, `skipped`, and `failed`:

```{code-block} python
from pathlib import Path

from click_extra import load_test_plan, run_test_plan

cases = list(load_test_plan(Path("plan.toml")))
counter = run_test_plan("weather", cases, jobs=4)
if counter["failed"]:
    raise SystemExit(1)
```

Build cases directly when a plan is computed rather than read from a file (this path needs no parser at all):

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
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```

## Future directions

The current design is a declarative list of directives. Two points of comparison suggest where it could go next.

Click Extra's [`click:run` and `click:source` Sphinx directives](sphinx.md) apply the same run-and-check idea from the documentation side: they execute a CLI in-process while the docs build and assert on its output, so every example doubles as a test. A test plan does it at the subprocess level instead, against any binary. Letting a documented example and a test case share one source is an open avenue.

[scrut](https://github.com/facebookincubator/scrut) is a standalone toolkit aimed at the same black-box CLI testing problem, with a different authoring model: expectations are written inline beneath each command in a Markdown or Cram file, and `scrut update` regenerates them. I came across it after building this feature for my own needs, so the resemblance is convergence, not lineage. Its snapshot-style workflow (generate and refresh expectations instead of hand-writing them), per-case environment and working-directory controls, and glob expectations are the directions worth weighing for a later revision.
