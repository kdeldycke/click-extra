# {octicon}`cpu` Jobs

A pre-configured `--jobs` option to control parallel execution. Defaults to one fewer than available CPU cores, leaving one core free for the main process and system tasks.

The option itself does not drive any concurrency: it only captures the user's intent.

```{tip}
The resolved (clamped, validated) job count is published on `ctx.meta` as `JOBS` for downstream code to consume. See the [available keys](context.md#available-keys) table to read it from your own callbacks.
```

## Usage

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

### Warnings

When the requested value is below 1, it is clamped to 1 and a warning is logged. When it exceeds available CPU cores, a warning is logged but the value is honored.

## `click_extra.jobs` API

```{eval-rst}
.. autoclasstree:: click_extra.jobs
   :strict:

.. automodule:: click_extra.jobs
   :members:
   :undoc-members:
   :show-inheritance:
```
