# {octicon}`meter` Pytest

`click_extra.pytest` is a [Pytest plugin](https://docs.pytest.org/en/stable/how-to/writing_plugins.html) registered through the `pytest11` entry point. Installing it is all the wiring there is: its fixtures are available to every test, with nothing to import and no `conftest.py` to write. Beside them, the module exposes plain helpers a test module imports directly.

````{important}
For these helpers to work, you need to install `click_extra`'s additional dependencies from the `pytest` [extra group](install.md#extra-dependencies):

```{code-block} shell-session
$ uv pip install click-extra[pytest]
```
````

## Utility functions

### Covering every decorator

Click, Cloup and Click Extra each provide their own `command`, `group`, `option` and `argument` decorators, usable with or without parenthesis. A behavior meant to hold everywhere has to be checked against all of them, and {py:func}`~click_extra.pytest.command_decorators` and {py:func}`~click_extra.pytest.option_decorators` expand that matrix into ready-made [Pytest parameters](https://docs.pytest.org/en/stable/how-to/parametrize.html):

```{python:run}
:show-source:
from click_extra.pytest import command_decorators

for param in command_decorators():
    print(param.id)
```

Each keyword carves the matrix down to the cells a test cares about:

| Keyword                              | Effect                                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `no_commands` / `no_groups`          | Drop the `command` or the `group` half. {py:func}`~click_extra.pytest.command_decorators` only.  |
| `no_options` / `no_arguments`        | Drop the `option` or the `argument` half. {py:func}`~click_extra.pytest.option_decorators` only. |
| `no_click` / `no_cloup` / `no_extra` | Drop one framework's row.                                                                        |
| `with_parenthesis`                   | Emit the `decorator()` variant beside the bare `decorator` one. On by default.                   |
| `with_types`                         | Pair each decorator with a set of tags, so a test can branch on what it was handed.              |

```{python:run}
:show-source:
from click_extra.pytest import option_decorators

for param in option_decorators(no_arguments=True, with_parenthesis=False, with_types=True):
    decorator, tags = param.values
    print(f"{param.id:20} {sorted(tags)}")
```

Feed either one to `parametrize` and build the CLI inside the test body, from the decorator the parameter carries:

```{code-block} python
:caption: `test_forecast.py`
import click
import pytest

from click_extra.pytest import command_decorators


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
def test_unit_option(invoke, cmd_decorator):
    @cmd_decorator
    @click.option("--unit", default="celsius")
    def forecast(unit):
        click.echo(f"Temperature in {unit}.")

    result = invoke(forecast, "--unit", "fahrenheit")
    assert result.exit_code == 0
    assert result.stdout == "Temperature in fahrenheit.\n"
```

Cases are named after the decorator they carry (`click.command`, `cloup.command()`, …), so a failure points at the framework and the calling convention that broke. The bare Cloup variants come pre-marked with `skip_naked`, since [Cloup does not support parenthesis-less decorators](https://github.com/janluke/cloup/issues/127): a run reports those cases as skipped instead of failing.

### Ready-made patterns

Every Click Extra command inherits a long list of options and, under `--verbosity DEBUG`, a fixed preamble of log lines. Asserting on a help screen or a debug trace therefore means transcribing output nobody wrote, and re-transcribing it whenever the defaults move. The module ships that boilerplate as regular expressions instead:

| Pattern                                   | Matches                                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `default_options_uncolored_help`          | The default options block closing the help screen.                                                     |
| `default_debug_uncolored_logging`         | The two lines raising the logger levels.                                                               |
| `default_debug_uncolored_config`          | The configuration-file search trace.                                                                   |
| `default_debug_uncolored_version_details` | The dump of the version-string template variables.                                                     |
| `default_debug_uncolored_log_start`       | The three above, concatenated: everything a `--verbosity DEBUG` run emits before the CLI's own output. |
| `default_debug_uncolored_log_end`         | The two lines restoring the logger levels on exit.                                                     |
| `default_debug_uncolored_verbose_log`     | The line `--verbose` prints for each repetition.                                                       |
| `default_debug_uncolored_quiet_log`       | The same for `--quiet`.                                                                                |

Each has a `colored` twin under the same name (`default_options_colored_help`, `default_debug_colored_config`, …), carrying the ANSI codes the same output has when colors are on.

They are fragments, so a test concatenates the part it wrote itself with the part it inherited:

```{python:run}
:show-source:
:hide-results:
from click_extra import command, echo, option
from click_extra.pytest import default_options_uncolored_help
from click_extra.testing import CliRunner, regex_fullmatch_line_by_line


@command
@option("--unit", default="celsius")
def forecast(unit):
    """Print the temperature of each city."""
    echo(f"Temperature in {unit}.")


result = CliRunner().invoke(forecast, "--help", color=False)

regex_fullmatch_line_by_line(
    r"Usage: forecast \[OPTIONS\]\n"
    r"\n"
    r"  Print the temperature of each city\.\n"
    r"\n"
    r"Options:\n"
    r"  --unit TEXT                  \[default: celsius\]\n" + default_options_uncolored_help,
    result.stdout,
)
```

That block runs on every documentation build: only the four lines the CLI actually owns are written out, and the rest of the screen is asserted by reference. Match the colored twin against a run keeping its ANSI codes, described in [Colors](testing.md#colors).

## Fixtures

| Fixture                                            | Provides                                                                                              |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| {py:func}`~click_extra.pytest.runner`              | A {py:class}`~click_extra.testing.CliRunner` in an isolated filesystem, with a pinned home directory. |
| {py:func}`~click_extra.pytest.invoke`              | Shorthand for that runner's `invoke` method.                                                          |
| {py:func}`~click_extra.pytest.create_config`       | A callable writing a configuration file into `tmp_path`.                                              |
| {py:func}`~click_extra.pytest.isolated_app_dir`    | A fresh, empty directory standing in for the host configuration folder.                               |
| {py:func}`~click_extra.pytest.assert_output_regex` | An assert-like callable comparing output to a regular expression.                                     |

### `runner` and `invoke`

{py:func}`~click_extra.pytest.runner` yields a {py:class}`~click_extra.testing.CliRunner` from inside an isolated filesystem, with `HOME` and its platform equivalents (`USERPROFILE`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA`) pointed at an empty subdirectory of it. A test therefore gets the same answers on a developer's machine and on a hermetic builder, both for the working directory the CLI writes into and for the configuration paths it derives from the home directory.

{py:func}`~click_extra.pytest.invoke` is that runner's `invoke` method, which is the one most tests want:

```{code-block} python
:caption: `test_forecast.py`
def test_default_unit(invoke):
    result = invoke(forecast)
    assert result.exit_code == 0
    assert result.stdout == "Temperature in celsius.\n"
```

See [CLI testing](testing.md) for what `invoke` accepts and what it gives back.

```{warning}
The home directory is pinned per test, but a module-global cache filled from inside one is not. A cache first populated during a test records what a home-less environment answered, and keeps serving that for the rest of the worker's session. Seed such a cache from a session-scoped fixture, which runs before the first test and outside this isolation.
```

### `create_config`

{py:func}`~click_extra.pytest.create_config` writes a configuration file under `tmp_path` and returns its path, creating any missing parent directory along the way. Hand that path to `--config` to exercise a CLI against a controlled file:

```{code-block} python
:caption: `test_forecast.py`
def test_unit_from_config(invoke, create_config):
    config = create_config("forecast.toml", '[forecast]\nunit = "fahrenheit"\n')
    result = invoke(forecast, "--config", config)
    assert result.exit_code == 0
    assert result.stdout == "Temperature in fahrenheit.\n"
```

The path travels unconverted because `invoke` casts every argument to a string for you, as described in [Composing arguments](testing.md#composing-arguments).

### `isolated_app_dir`

Without `--config`, a Click Extra CLI [searches the host configuration folder](config.md#default-folder): `~/Library/Application Support/<app>` on macOS, `~/.config/<app>` on Unix, `%APPDATA%\<app>` on Windows. Any file sitting there bleeds into every in-process invocation, so a suite passes or fails on the developer's own configuration.

{py:func}`~click_extra.pytest.isolated_app_dir` repoints {py:func}`click.get_app_dir` at a per-test temporary directory, whatever application name is asked for, and returns it. Plant a file in it to exercise the default search against a controlled one:

```{code-block} python
:caption: `test_forecast.py`
def test_config_autodiscovery(invoke, isolated_app_dir):
    (isolated_app_dir / "forecast.toml").write_text(
        '[forecast]\nunit = "fahrenheit"\n', encoding="utf-8"
    )
    result = invoke(forecast)
    assert result.stdout == "Temperature in fahrenheit.\n"
```

To make a whole suite hermetic, alias it to an autouse fixture:

```{code-block} python
:caption: `conftest.py`
import pytest


@pytest.fixture(autouse=True)
def isolate_user_config(isolated_app_dir):
    return isolated_app_dir
```

### `assert_output_regex`

{py:func}`~click_extra.pytest.assert_output_regex` compares output to a pattern line by line, and reports the first line that disagrees with a {py:func}`difflib.ndiff` diff pointing at the offending characters. It is the assertion form of {py:func}`~click_extra.testing.regex_fullmatch_line_by_line`, and the natural consumer of the [ready-made patterns](#ready-made-patterns):

```{code-block} python
:caption: `test_forecast.py`
from click_extra.pytest import default_options_uncolored_help


def test_help_screen(invoke, assert_output_regex):
    result = invoke(forecast, "--help", color=False)
    assert_output_regex(
        result.stdout,
        r"Usage: forecast \[OPTIONS\]\n"
        r"\n"
        r"Options:\n"
        r"  --unit TEXT                  \[default: celsius\]\n"
        + default_options_uncolored_help,
    )
```

## `click_extra.pytest` API

```{eval-rst}
.. autoclasstree:: click_extra.pytest
   :strict:

.. automodule:: click_extra.pytest
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
