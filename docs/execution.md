# {octicon}`play` Execution

Click Extra bundles a few pre-configured options that control how a CLI runs: how long it takes (`--time`), how many parallel jobs it may use (`--jobs`), and what exit code it returns (`-0`/`--zero-exit`). Each publishes its resolved value on `ctx.meta` for downstream code to consume.

## Timer

Click Extra can measure the execution time of a CLI via a dedicated `--time`/`--no-time` option.

Here how to use the standalone decorator:

```{click:source}
:emphasize-lines: 6
from time import sleep
from click import command, echo, pass_context
from click_extra import timer_option

@command
@timer_option
def timer():
    sleep(0.2)
    echo("Hello world!")
```

```{click:run}
:emphasize-lines: 5
result = invoke(timer, args=["--help"])
assert "--time / --no-time" in result.stdout
```

```{click:run}
:emphasize-lines: 3
import re

result = invoke(timer, ["--time"])
assert re.fullmatch(
    r"Hello world!\n"
    r"Execution time: (?P<time>[0-9.]+) seconds.\n",
    result.stdout,
)
```

You can get the timestamp of the CLI start from the context:

```{click:source}
:emphasize-lines: 8
from click import command, echo, pass_context
from click_extra import timer_option

@command
@timer_option
@pass_context
def timer_command(ctx):
    start_time = ctx.meta["click_extra.start_time"]
    echo(f"Start timestamp: {start_time}")
```

```{click:run}
import re

result = invoke(timer_command, args=["--time"])
assert re.fullmatch(
    r"Start timestamp: (?P<time>[0-9.]+)\n"
    r"Execution time: (?P<elapsed>[0-9.]+) seconds.\n",
    result.stdout,
)
```

## Parallel jobs

A pre-configured `--jobs` option to control parallel execution. Defaults to one fewer than available CPU cores, leaving one core free for the main process and system tasks.

The option itself does not drive any concurrency: it only captures the user's intent.

```{click:source}
from click import command, echo, pass_context
from click_extra import jobs_option

@command
@jobs_option
@pass_context
def build(ctx):
    """Build the project."""
    jobs = ctx.meta["click_extra.jobs"]
    echo(f"Building with {jobs} parallel jobs.")
```

```{click:run}
result = invoke(build, args=["--help"])
assert "--jobs" in result.stdout
assert result.exit_code == 0
```

```{click:run}
result = invoke(build, args=["--jobs", "4"])
assert result.exit_code == 0
assert "Building with 4 parallel jobs." in result.stdout
```

```{warning}
When the requested value is below 1, it is clamped to 1 and a warning is logged. When it exceeds available CPU cores, a warning is logged but the value is honored.
```

```{tip}
The resolved (clamped, validated) job count is published on `ctx.meta` as `JOBS` for downstream code to consume. See the [available keys](context.md#available-keys) table to read it from your own callbacks.
```

## Zero exit code

A pre-configured `-0`/`--zero-exit` option flag, following the convention popularized by linters and static analysers: they exit with a non-zero code whenever they report findings, so automation can gate on it. Setting this flag flips that behavior, so the CLI returns `0` as long as it ran to completion, reserving non-zero codes for actual execution failures.

The option itself does not alter the exit code: it only captures the user's intent.

```{click:source}
from click import command, echo, pass_context
from click_extra import zero_exit_option

@command
@zero_exit_option
@pass_context
def inspect(ctx):
    """Inspect a basket of fruits."""
    bruised = 2
    echo(f"Found {bruised} bruised fruits.")
    if bruised and not ctx.meta["click_extra.zero_exit"]:
        ctx.exit(1)
```

```{click:run}
result = invoke(inspect, args=["--help"])
assert "--zero-exit" in result.stdout
assert result.exit_code == 0
```

By default the command reports a non-zero exit code when it finds problems:

```{click:run}
result = invoke(inspect)
assert result.exit_code == 1
assert "Found 2 bruised fruits." in result.stdout
```

With `--zero-exit` (or its `-0` shorthand) the command still reports its findings but always exits with `0`:

```{click:run}
result = invoke(inspect, args=["--zero-exit"])
assert result.exit_code == 0
assert "Found 2 bruised fruits." in result.stdout
```

```{tip}
The resolved flag is published on `ctx.meta` as `ZERO_EXIT` for downstream code to consume. See the [available keys](context.md#available-keys) table to read it from your own callbacks.
```

## `click_extra.execution` API

```{eval-rst}
.. autoclasstree:: click_extra.execution
   :strict:

.. automodule:: click_extra.execution
   :members:
   :undoc-members:
   :show-inheritance:
```
