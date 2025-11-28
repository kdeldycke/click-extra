# {octicon}`stopwatch` Timer

## Option

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

### Get start time

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

result = invoke(timer_command)
assert re.fullmatch(
    r"Start timestamp: (?P<time>[0-9.]+)\n",
    result.stdout,
)
```

## `click_extra.timer` API

```{eval-rst}
.. autoclasstree:: click_extra.timer
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.timer
   :members:
   :undoc-members:
   :show-inheritance:
```
