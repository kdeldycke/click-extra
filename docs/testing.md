# {octicon}`shield-check` CLI testing

{py:class}`~click_extra.testing.CliRunner` runs a Click CLI **in-process**: the command object is imported, its callback executes inside the test process, and its streams are captured in memory. It is a drop-in replacement for [`click.testing.CliRunner`](https://click.palletsprojects.com/en/stable/testing/), and what the [`runner` and `invoke` fixtures](pytest.md#fixtures) hand to a test.

```{tip}
For the black-box counterpart, which spawns the command as a subprocess and never imports it, see [test suites](test-suite.md). Both render a run with the same [execution trace](#rendering-a-run).
```

## Invoking a command

Take a CLI reporting the temperature of each city it is given:

```{python:source}
from click_extra import argument, command, echo, option


@command
@option("--unit", default="celsius")
@argument("cities", nargs=-1)
def forecast(unit, cities):
    """Print the temperature of each city."""
    if not cities:
        echo("No city to report on.", err=True)
    for city in cities:
        echo(f"{city}: 21 {unit}")
```

Hand it to a runner. The command is the first positional argument, and everything after it is a command-line argument:

```{python:run}
:show-source:
:language: ansi-output
from click_extra.testing import CliRunner

runner = CliRunner()
result = runner.invoke(forecast, "--unit", "fahrenheit", "Oslo", "Lisbon")

assert result.exit_code == 0
assert result.stdout == "Oslo: 21 fahrenheit\nLisbon: 21 fahrenheit\n"
```

Passing the arguments as a list under an `args` keyword, the way vanilla Click expects them, works too and can be mixed with the positional form.

Every invocation prints the [execution trace](#rendering-a-run) reproduced above, pass or fail. It is what a failing test shows in its captured output, so a broken assertion comes with the session that produced it instead of a bare exit code.

## Composing arguments

Positional arguments are flattened, so a nested structure of lists and tuples is spelled out as-is. `None` values are dropped, and every remaining item is cast to a string, which lets a {py:class}`~pathlib.Path` travel unconverted:

```{python:run}
:show-source:
:language: ansi-output
from pathlib import Path

result = runner.invoke(forecast, ["Oslo", None, ["Lisbon", (Path("Kyoto"),)]])

assert result.exit_code == 0
assert result.stdout == "Oslo: 21 celsius\nLisbon: 21 celsius\nKyoto: 21 celsius\n"
```

That is {py:func}`~click_extra.execution.args_cleanup` doing the work, and it is what makes a [parametrized test](https://docs.pytest.org/en/stable/example/parametrize.html) readable: each case contributes its own fragment of the command line, and an optional fragment collapses to `None` instead of forcing the test to assemble the list itself.

```{code-block} python
:caption: `test_forecast.py`
import pytest


@pytest.mark.parametrize("unit_flag", (None, ("--unit", "fahrenheit")))
@pytest.mark.parametrize("cities", (("Oslo",), ("Oslo", "Lisbon")))
def test_forecast(invoke, unit_flag, cities):
    result = invoke(forecast, unit_flag, cities)
    assert result.exit_code == 0
```

## Reading the result

{py:class}`~click_extra.testing.Result` carries the exit code, the captured streams and whatever exception escaped the callback:

| Attribute             | Content                                                   |
| --------------------- | --------------------------------------------------------- |
| `exit_code`           | Process exit status.                                      |
| `stdout`              | Standard output alone.                                    |
| `stderr`              | Standard error alone.                                     |
| `output`              | Both streams, interleaved in the order they were written. |
| `exception`           | The exception that escaped the callback, if any.          |
| `formatted_exception` | Its full traceback, as a string, or `None`.               |

The two streams stay addressable separately, which is how a test pins a diagnostic to the stream it belongs on:

```{python:run}
:show-source:
:language: ansi-output
result = runner.invoke(forecast)

assert result.exit_code == 0
assert result.stdout == ""
assert result.stderr == "No city to report on.\n"
```

When the callback raises, the runner catches the exception, sets a non-zero `exit_code`, and prints the traceback below the trace. {py:attr}`~click_extra.testing.Result.formatted_exception` keeps that traceback available, and `repr(result)` embeds it, so an `assert result.exit_code == 0` that fails reports where the CLI died rather than which exception class it was. Pass `catch_exceptions=False` to let the exception propagate into the test instead.

## Colors

ANSI codes survive the trip only when asked for. `color` accepts one more value than Click's:

| `color=`   | Captured streams | `Context.color` |
| ---------- | ---------------- | --------------- |
| `None`     | Stripped         | `None`          |
| `False`    | Stripped         | `None`          |
| `True`     | Kept             | `None`          |
| `"forced"` | Kept             | `True`          |

`color=True` keeps the codes in the captured output, but the invoked CLI still sees an uncolored context and takes its uncolored branch. `color="forced"` covers both: it keeps the codes *and* initializes `Context.color` to `True`, which vanilla Click cannot express because the two meanings collide on one parameter name ([pallets/click#2110](https://github.com/pallets/click/issues/2110)). Click Extra routes the second one through a patched `main()` call, so any other `Context` keyword named like an `invoke()` parameter gets through as well.

```{python:source}
import click

from click_extra import style


@click.command
@click.pass_context
def report(ctx):
    click.echo(style("Sunny", fg="yellow") + " in Lisbon.")
    click.echo(f"Context.color is {ctx.color!r}")
```

```{python:run}
:show-source:
:language: ansi-output
result = runner.invoke(report, color="forced")

assert "\x1b[33mSunny\x1b[0m in Lisbon.\n" in result.stdout
assert "Context.color is True\n" in result.stdout
```

Setting `color=False` goes one step further than Click's stripping and scrubs the result bytes, so a CLI writing raw escape sequences past Click's own machinery still yields clean text. To keep the codes on every invocation of a suite without touching each call, set the `force_color` class attribute on {py:class}`~click_extra.testing.CliRunner`: it pins every run to the `color=True` row above.

```{note}
The command above is a plain Click one on purpose: nothing but the runner decides its colors. A Click Extra command owns that decision itself, through its [`--color`/`--no-color` options](colorize.md#color-flag) and the `NO_COLOR` and `FORCE_COLOR` environment variables, which have the last word over whatever the runner was told.
```

## Rendering a run

{py:func}`~click_extra.testing.render_cli_run` produces the trace on its own, from either an in-process {py:class}`click.testing.Result` or a {py:class}`subprocess.CompletedProcess`. Both are normalized into a {py:class}`~click_extra.testing.StreamView` first, so a black-box run and an in-process one read identically:

```{python:run}
:show-source:
:language: ansi-output
import subprocess
import sys

from click_extra.testing import render_cli_run

process = subprocess.run(
    (sys.executable, "-c", "print('Lisbon: 21 celsius')"),
    capture_output=True,
    text=True,
    encoding="utf-8",
)

print(render_cli_run(("forecast", "Lisbon"), process, env={"FORECAST_UNIT": "celsius"}))
```

The first line is the command as the user would have typed it, environment assignments included. Each captured stream then gets its own labelled, indented block, and the exit code closes the trace. A stream that captured nothing is left out entirely: a subprocess run with `stderr=STDOUT` reports a single interleaved `<output>` stream, while separate streams give the `<stdout>` and `<stderr>` pair.

## Matching output against a regex

Comparing a wall of terminal output to an expected string reports the whole wall on failure, and leaves the reader to find the offending character. {py:func}`~click_extra.testing.regex_fullmatch_line_by_line` matches the pattern one line at a time and reports the first line that disagrees:

```{python:run}
:show-source:
from click_extra.testing import RegexLineMismatch, regex_fullmatch_line_by_line

try:
    regex_fullmatch_line_by_line(
        r"Lisbon: \d+ celsius\nOslo: \d+ fahrenheit\n",
        "Lisbon: 21 celsius\nOslo: 9 celsius\n",
    )
except RegexLineMismatch as ex:
    print(ex)
```

The pattern is split on its `\n` tokens, so it is written as one raw string mirroring the expected output, not as a list of per-line patterns. A pattern matching in full short-circuits the loop, and only a mismatch pays for the line-by-line pass.

The reported pattern goes through {py:func}`~click_extra.testing.unescape_regex`, the inverse of {py:func}`re.escape`, which strips the backslashes an escaped literal is littered with so the two sides of the report line up visually:

```{python:run}
:show-source:
from click_extra.testing import unescape_regex

assert unescape_regex(r"Usage: forecast \[OPTIONS\] \[CITIES\]\.\.\.") == (
    "Usage: forecast [OPTIONS] [CITIES]..."
)
print(unescape_regex(r"Usage: forecast \[OPTIONS\] \[CITIES\]\.\.\."))
```

The [`assert_output_regex` fixture](pytest.md#assert-output-regex) wraps that comparison into an assertion carrying a character-level diff, and the [ready-made patterns](pytest.md#ready-made-patterns) shipped with it cover the help screen and debug logs Click Extra adds to every CLI.

## `click_extra.testing` API

```{eval-rst}
.. autoclasstree:: click_extra.testing
   :strict:

.. automodule:: click_extra.testing
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
