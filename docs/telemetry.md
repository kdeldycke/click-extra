# {octicon}`broadcast` Telemetry

A simple pre-configured `--telemetry`/`--no-telemetry` option flag, that is respecting the [proposed `DO_NOT_TRACK` environment variable](https://consoledonottrack.com) as a unified standard to opt-out of telemetry for TUI/console apps.

It does nothing else.

```{click:source}
from click_extra import command, context, echo, pass_context, telemetry_option

@command
@telemetry_option
@pass_context
def orchard(ctx):
    """Count the apple trees."""
    echo(f"Telemetry: {context.get(ctx, context.TELEMETRY)}")
```

## `DO_NOT_TRACK` precedence

A truthy `DO_NOT_TRACK` turns telemetry off. Most specific first:

1. `--telemetry` or `--no-telemetry` on the command line;
2. `DO_NOT_TRACK` in the environment;
3. `<CLI>_TELEMETRY` in the environment;
4. `telemetry` in the CLI's [configuration file](config.md);
5. the built-in default, off.

This ranks `DO_NOT_TRACK` above the variable of the option and above the configuration file, where the other machine-wide variables, like [`CLICK_EXTRA_THEME`](theme.md#precedence), rank below both. `DO_NOT_TRACK` is a consumer-protection opt-out: a user exports it once to refuse tracking from every tool, and a configuration file a project ships, or a variable a wrapper sets, must not opt that user back in. Only the command line, which the user types, outranks it:

```{click:run}
import os

os.environ["DO_NOT_TRACK"] = "1"
os.environ["ORCHARD_TELEMETRY"] = "1"
try:
    result = invoke(orchard)
    flag_result = invoke(orchard, args=["--telemetry"])
finally:
    os.environ.pop("DO_NOT_TRACK", None)
    os.environ.pop("ORCHARD_TELEMETRY", None)

assert result.exit_code == 0
assert result.output == "Telemetry: False\n"
assert flag_result.exit_code == 0
assert flag_result.output == "Telemetry: True\n"
```

## `click_extra.telemetry` API

```{eval-rst}
.. autoclasstree:: click_extra.telemetry
   :strict:

.. automodule:: click_extra.telemetry
   :no-index:
   :members:
   :undoc-members:
   :show-inheritance:
```
