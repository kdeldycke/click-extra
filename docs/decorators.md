# {octicon}`issue-opened` Decorators

Click Extra's decorators (`@command`, `@group`, `@option`, `@argument`, `@version_option`, the full `@*_option` family) are produced by a single factory that wraps cloup's originals with three extra behaviors:

1. **Subclass-enforced `cls=`**: every `@command` / `@group` always yields an `ExtraCommand` / `ExtraGroup` (or a user-supplied subclass thereof), so click-extra's machinery — config loading, theme registry, `--show-params` introspection — can't be silently bypassed by passing a vanilla `click.Command` class.
2. **Default-parameter injection**: `default_extra_params()` (the global option set: `--time`, `--config`, `--color`, `--theme`, …) is passed as a *callable*, so each command gets its own freshly-instantiated option list rather than sharing the same mutable instances.
3. **Optional-parenthesis decoration**: `@command` and `@command()` are both legal call forms, matching the convention [requested in Cloup #127](https://github.com/janluke/cloup/issues/127#issuecomment-1264704896).

If you only ever use the decorators click-extra ships out of the box, you don't need to read further. This page is for downstream code that wants to wire its own `@my_option` decorator into the same factory.

## `decorator_factory(dec, *new_args, **new_defaults)`

Clone a base decorator with a new set of default arguments, while validating that any user-supplied `cls=` is a subclass of the factory's `cls=`. The result is itself a decorator that accepts the same arguments as `dec` and forwards them with the new defaults merged in.

The signature reads like this in click-extra's own decorator file:

```python
# click_extra/decorators.py
from .commands import ExtraCommand, ExtraGroup, default_extra_params

command = decorator_factory(
    dec=cloup.command,
    cls=ExtraCommand,
    params=default_extra_params,
)
group = decorator_factory(
    dec=cloup.group,
    cls=ExtraGroup,
    params=default_extra_params,
)
```

After that wiring, `@command` always produces an `ExtraCommand`, and `@command(cls=MyExtraCommand)` is accepted *only if* `MyExtraCommand` is a subclass of `ExtraCommand`. Anything else raises a `TypeError` with a full MRO listing of the offending class, so the caller sees *why* their override was rejected:

```{python:run}
import click

from click_extra import command


# Subclass of ExtraCommand: accepted.
from click_extra.commands import ExtraCommand


class MyExtraCommand(ExtraCommand):
    pass


@command(cls=MyExtraCommand)
def fine():
    pass


print(type(fine).__name__)


# Plain click.Command: rejected at decoration time.
try:

    @command(cls=click.Command)
    def bad():
        pass

except TypeError as exc:
    print(repr(exc))
```

### Callable `params=`

When the factory is given `params=` as a callable (e.g. `default_extra_params`), it's invoked once per decorated command so each command receives a fresh list of option instances. Without this indirection, two commands declared in the same module would share the *same* `TimerOption` instance, the *same* `ConfigOption` instance, and so on — which sounds harmless but produces subtle bugs (a callback registered by one command runs again when the second command exits, the parameter source map carries stale entries, …). Pass any zero-argument callable that returns a list of `click.Parameter` instances.

## `allow_missing_parenthesis(dec_factory)`

A small wrapper that lets a decorator-factory be called *either* with parentheses (the standard `@dec()` form) *or* without (`@dec`). `decorator_factory` applies it automatically to every decorator it produces.

```{python:run}
from click_extra.decorators import allow_missing_parenthesis


def my_factory(message="default"):
    """Decorator factory: returns the decorator with a captured message."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            print(message)
            return func(*args, **kwargs)

        return wrapper

    return decorator


# Without the wrapper, only `@my_factory()` (with parens) works.
flexible = allow_missing_parenthesis(my_factory)


@flexible
def a():
    pass


@flexible()
def b():
    pass


@flexible(message="hi")
def c():
    pass


a()
b()
c()
```

## The standard decorator suite

Every default option ships with a matching decorator built via `decorator_factory`:

| Decorator                | Wraps                                                          |
| ------------------------ | -------------------------------------------------------------- |
| `command`                | `cloup.command(cls=ExtraCommand, params=default_extra_params)` |
| `group`                  | `cloup.group(cls=ExtraGroup, params=default_extra_params)`     |
| `lazy_group`             | `group(cls=LazyGroup)`                                         |
| `option`                 | `cloup.option(cls=Option)`                                     |
| `argument`               | `cloup.argument(cls=Argument)`                                 |
| `help_option`            | `click.decorators.help_option(*DEFAULT_HELP_NAMES)`            |
| `version_option`         | `option(cls=ExtraVersionOption)`                               |
| `color_option`           | `option(cls=ColorOption)`                                      |
| `config_option`          | `option(cls=ConfigOption)`                                     |
| `no_config_option`       | `option(cls=NoConfigOption)`                                   |
| `validate_config_option` | `option(cls=ValidateConfigOption)`                             |
| `jobs_option`            | `option(cls=JobsOption)`                                       |
| `show_params_option`     | `option(cls=ShowParamsOption)`                                 |
| `table_format_option`    | `option(cls=TableFormatOption)`                                |
| `telemetry_option`       | `option(cls=TelemetryOption)`                                  |
| `theme_option`           | `option(cls=ThemeOption)`                                      |
| `timer_option`           | `option(cls=TimerOption)`                                      |
| `verbose_option`         | `option(cls=VerboseOption)`                                    |
| `verbosity_option`       | `option(cls=VerbosityOption)`                                  |

Every entry in this list is an `allow_missing_parenthesis`-wrapped factory, so `@theme_option` and `@theme_option()` are both legal, and `@theme_option(default="light")` overrides the default while keeping the click-extra subclass guarantee.

## Rolling your own

To plug a custom `ExtraOption` subclass into the same machinery, instantiate `decorator_factory(dec=option, cls=MyOption)`:

```{python:run}
from click_extra import command, decorators, option
from click_extra.parameters import ExtraOption


class CounterOption(ExtraOption):
    """A simple ``--counter`` option with an enforced default of 0 and type int."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", 0)
        kwargs.setdefault("type", int)
        super().__init__(*args, **kwargs)


counter_option = decorators.decorator_factory(
    dec=option,
    cls=CounterOption,
)


@command
@counter_option("--retries")
@counter_option("--workers")
def cli(retries, workers):
    pass


# The factory honors @counter_option (without parens) and @counter_option(...)
# (with parens) interchangeably, and produces a CounterOption instance with
# the enforced defaults applied at decoration time.
retries = next(p for p in cli.params if p.name == "retries")
workers = next(p for p in cli.params if p.name == "workers")
print(f"--retries: type={type(retries).__name__}, default={retries.default}")
print(f"--workers: type={type(workers).__name__}, default={workers.default}")
```

This pattern is how click-extra builds every `*_option` decorator listed above, and how downstream projects can extend the suite without re-implementing the subclass-validation / fresh-params machinery.

## `click_extra.decorators` API

```{eval-rst}
.. automodule:: click_extra.decorators
   :members:
   :undoc-members:
   :show-inheritance:
```
