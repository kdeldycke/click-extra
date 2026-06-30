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

A pre-configured `--jobs` option to control parallel execution. It accepts an integer, or one of two keywords: `auto` (the default: one fewer than the available logical CPU cores, leaving a core free for the main process and system tasks) and `max` (every available logical CPU core). A value of `0` disables parallelism and runs sequentially.

The option itself does not drive any concurrency: it only captures the user's intent.

```{important}
The core count is the number of **logical** CPUs reported by Python's `os.cpu_count()`: hardware threads, not physical cores. On a CPU with simultaneous multi-threading (Intel Hyper-Threading, AMD SMT) a 4-physical-core chip reports `8`. This is deliberately the logical count, since subprocess- and I/O-bound work overlaps well across hardware threads. It can differ from the physical-core counts used elsewhere (`psutil.cpu_count(logical=False)`, or pytest-xdist's `-n auto`), so `--jobs auto` may pick a higher number than a physical-core heuristic would.
```

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
assert "auto" in result.stdout
assert "max" in result.stdout
assert result.exit_code == 0
```

```{click:run}
result = invoke(build, args=["--jobs", "4"])
assert result.exit_code == 0
assert "Building with 4 parallel jobs." in result.stdout
```

The `auto` and `max` keywords resolve to a core count, keeping the same command portable across machines with different CPU counts:

```{click:run}
result = invoke(build, args=["--jobs", "max"])
assert result.exit_code == 0
assert "parallel jobs." in result.stdout
```

```{warning}
A value of `0` disables parallelism: it is rounded up to `1` and a warning notes that execution will run sequentially. Negative values are likewise clamped to `1`. When the count exceeds the available logical CPU cores, a warning is logged but the value is honored.
```

```{warning}
`auto` and `max` express a wish for parallelism, but on hosts with few logical CPUs they resolve to a single job and run sequentially: `max` on a single-core host, or `auto` on a one- or two-core host (it reserves one core). A warning is then logged, so the silent sequential fallback is not mistaken for parallel execution. An explicit `--jobs 1` is treated as a deliberate sequential choice and stays silent.
```

```{tip}
The resolved (clamped, validated) job count is published on `ctx.meta` as `JOBS` for downstream code to consume. See the [available keys](context.md#available-keys) table to read it from your own callbacks. It is also logged at info level alongside the host's `os.cpu_count()`, so `--verbosity INFO` reveals how many workers a `--jobs` command will use.
```

## Running jobs in parallel

`run_jobs(func, items)` maps `func` over `items` using the resolved `--jobs` count, so a command with `@jobs_option` parallelizes its work with no extra plumbing. It reads the worker count from the context (or an explicit `jobs=` override), runs sequentially when that count is `1` or there is a single item, and otherwise spreads the work across a thread pool. Results are yielded in submission order, like `map`.

```{click:source}
from click import command, echo
from click_extra import jobs_option, run_jobs

@command
@jobs_option
def bake():
    """Bake several items in parallel."""
    items = ("apple", "banana", "cherry")
    for baked in run_jobs(str.upper, items):
        echo(f"Baked {baked}")
```

```{click:run}
result = invoke(bake, args=["--jobs", "2"])
assert result.exit_code == 0
assert "Baked APPLE" in result.stdout
```

The pool is thread-based, which fits the I/O- and subprocess-bound work CLIs usually parallelize (each child releases the GIL). With a single worker the run stays lazy, so a caller can stop on the first result, for example to abort on the first failure.

## Running lanes in parallel

Sometimes work cannot all run concurrently: a subset must be serialized relative to itself (a shared lock, a rate limit, one mailbox file read at a time, one package-manager backend) while still overlapping with unrelated subsets. `run_lanes(func, lanes)` groups items into *lanes*: a lane's own items run serially and in order on a single worker, while distinct lanes run concurrently up to the resolved `--jobs` count. `run_jobs` is the degenerate case where every lane holds a single item.

```{click:source}
from click import command, echo
from click_extra import jobs_option, run_lanes

@command
@jobs_option
def bake():
    """Bake several trays: items on a tray bake in order, trays bake in parallel."""
    trays = (("apple", "banana"), ("cherry",))
    for baked in run_lanes(str.upper, trays):
        echo(f"Baked {baked}")
```

```{click:run}
result = invoke(bake, args=["--jobs", "2"])
assert result.exit_code == 0
assert "Baked APPLE" in result.stdout
```

Concurrency is sized by the number of lanes (one worker per lane), and results are yielded in lane-submission order. Because a lane runs entirely on one worker, a stateful resource bound to that lane (a per-lane cache, a connection) is touched by only one thread and needs no lock.

## Resolving the job count

`run_jobs` and `run_lanes` decide their worker count internally, but a caller that must know it *before* fanning out (for example to pick a progress-rendering mode) can call `resolve_jobs(ctx, count)` directly. It returns the same number those helpers use: `1` (sequential) when there is no context, a single item, or `--jobs 1`, otherwise the resolved count capped at `count`. Passing `serial_at_debug=True` also collapses to sequential at `DEBUG` verbosity, where coherent per-worker log narration matters more than the speed-up; both helpers forward this flag.

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
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
