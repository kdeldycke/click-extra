# {octicon}`sync` Spinner

An indeterminate progress spinner for blocking work whose duration is unknown: a subprocess, a network call, a long query. Where [`click.progressbar`](https://click.palletsprojects.com/en/stable/api/#click.progressbar) needs a known length or an iterable to advance through, `Spinner` simply signals that something is happening.

It animates on a background thread, so the calling thread stays free to block on the work itself:

```python
from time import sleep

from click_extra import Spinner

with Spinner("Brewing tea"):
    sleep(5)
```

The spinner draws to `stderr` and is a no-op whenever that stream is not a terminal (a pipe, a file, a CI log), so redirected output and machine-readable formats stay clean. Reassign its `label` while it runs to reflect the current step, and set a `delay` so it only appears once an operation is genuinely slow.

## Use as a decorator

A `Spinner` doubles as a decorator, with or without parentheses. `@Spinner` wraps a function directly; `@Spinner("…")` configures the spinner first. Either way the function spins for the duration of every call and returns its result untouched.

```python
@Spinner  # Bare form: a default spinner.
def roast(batch):
    sleep(5)
    return batch


@Spinner("Roasting coffee", timer=True)  # Configured form.
def roast_slowly(batch):
    sleep(5)
    return batch
```

The one instance is shared across calls, which is right for sequential use; give concurrent callers their own spinner.

## Spin direction

Pass `reverse=True` to rotate the other way. It works with the default frames or any custom sequence:

```python
with Spinner("Chilling lemonade", reverse=True):
    sleep(5)
```

The animation source is just a sequence of strings. `click_extra.spinner` ships the default Braille `SPINNER_FRAMES` and a plain `ASCII_SPINNER_FRAMES` for terminals without Unicode glyphs; pass your own to `frames` for anything else.

## Spinner catalog

`SPINNERS` is a catalog of around 90 ready-made animations, each a `SpinnerPreset` bundling the frames and the interval they were tuned for. They are ported from [cli-spinners](https://github.com/sindresorhus/cli-spinners), the de-facto reference collection. Pick one with `spinner=`:

```python
from click_extra import Spinner, SPINNERS

with Spinner("Brewing tea", spinner=SPINNERS["moon"]):
    sleep(5)
```

The preset sets both the frames and the interval; an explicit `frames=` or `interval=` still overrides it. Because the spinner redraws the whole line instead of backspacing, the multi-character animations (`bouncingBar`, `pong`, `shark`, …) render correctly here, unlike in the upstream renderers that had to drop them.

### Full inventory

Every style is browsable from the CLI. On an interactive terminal `click-extra spinner` animates a live tour of the selection (`--all` for the whole catalog, `--random N` for a sample, or `--select name1,name2` for specific ones); `--table` prints the reference table below instead of animating. The Frames column previews each animation, and the Tour column is the dwell time the live tour spends on each — three full cycles, clamped to two-to-three seconds:

```{click:run}
from click_extra.cli import demo

result = invoke(demo, args=["--color", "spinner", "--all", "--table"])
assert result.exit_code == 0
assert "moon" in result.output
assert "bouncingBar" in result.output
assert "dots8Bit" in result.output
assert "Interval" in result.output
assert "Tour" in result.output
```

## Bell on completion

Set `beep=True` to ring the terminal bell once when the spinner stops, handy for a long task you walk away from. It rings only when the spinner was actually shown, so redirected or non-interactive runs stay quiet:

```python
with Spinner("Baking bread", beep=True):
    sleep(5)
```

## Printing while spinning

Because the spinner draws to `stderr`, results written to `stdout` never collide with the animation. To emit a line on the *same* stream as the spinner, use `echo()`: it erases the current frame, prints the message above the spinner, and lets the animation carry on underneath. A bare `print` would instead leave a frame glyph stranded mid-line.

```python
with Spinner("Picking apples") as spinner:
    for basket in range(3):
        sleep(2)
        spinner.echo(f"Filled basket {basket}")
```

## Parallel work

A `Spinner` drives a single line, so a pool of concurrent tasks does not need one apiece: one spinner can report on them all. The simplest way is to let the main thread update it as the tasks finish, through [`concurrent.futures.as_completed`](https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.as_completed).

Update the `label` for a running count:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep

from click_extra import Spinner

cities = ["Cairo", "Lima", "Oslo", "Paris", "Tokyo"]


def fetch(city):
    sleep(1)  # The blocking call: a download, a query, a subprocess.
    return city


with Spinner(f"Fetching forecasts (0/{len(cities)})") as spinner:
    with ThreadPoolExecutor() as pool:
        futures = [pool.submit(fetch, city) for city in cities]
        for done, _ in enumerate(as_completed(futures), 1):
            spinner.label = f"Fetching forecasts ({done}/{len(cities)})"
```

Or `echo()` a line as each task lands, leaving a trail of finished work that scrolls up while the spinner keeps turning below it:

```python
with Spinner("Fetching forecasts") as spinner:
    with ThreadPoolExecutor() as pool:
        futures = {pool.submit(fetch, city): city for city in cities}
        for future in as_completed(futures):
            spinner.echo(f"✓ {futures[future]}")
```

Both `label` and `echo()` are safe to touch while the animation runs, so a worker thread can stream its own progress mid-task rather than only reporting on completion. A genuine spinner *per* task, several rotating at once on their own lines, is a separate capability: it needs a coordinated multi-line region, which `Spinner` does not attempt.

## Styling and color

The spinner's glyph, label and timer are painted with a [`Style`](styling.md) instance — the very type Click Extra's [theme system](theme.md) is built on. The simplest customization is a foreground color:

```python
from click_extra import Spinner, Style

with Spinner("Counting sheep", style=Style(fg="cyan")):
    sleep(5)
```

A `Style` carries far more than a foreground color. Add a background with `bg`, and text attributes like `bold`, `dim`, `italic`, `underline`, `blink` or `reverse` — and combine them freely:

```python
with Spinner("Counting sheep", style=Style(fg="bright_white", bg="blue", bold=True)):
    sleep(5)
```

Colors accept any form [`click.style`](https://click.palletsprojects.com/en/stable/api/#click.style) understands: ANSI names (`"red"`, `"bright_magenta"`), 256-color indexes, `#rrggbb` hex strings, or `(r, g, b)` tuples. A `Style` carrying an unrenderable color or attribute is rejected with a `ValueError` at construction, so a typo fails fast instead of silently dying on the animation thread.

### Color follows the terminal, not the spinner

Color is decoupled from the animation: under `--no-color` or `NO_COLOR` the spinner keeps spinning, just in plain text (the `--progress` section below explains the rationale). Inside a Click Extra CLI the color follows the reconciled `--color`/`--no-color` flag; standalone it honors `FORCE_COLOR`, then `NO_COLOR`, then falls back to whether the terminal is interactive.

The same `Style` type colors the `ok()` / `fail()` finishers: they default to the theme's `success`/`error` style and take a `style=` override, covered in the *Success and failure* section below.

## Success and failure

Stopping the spinner (or leaving its context) erases it. To leave a result on screen instead, finish with `ok()` or `fail()`: each replaces the final frame with a kept line. The marker defaults to the theme's success/error glyph (`✓` / `✘`), painted with the active theme's `success`/`error` [`Style`](theme.md), so a finished spinner matches the rest of a themed CLI.

```python
with Spinner("Baking bread") as spinner:
    sleep(5)
    spinner.ok()  # ✓ Baking bread
```

Pass your own marker (`spinner.ok("done")`) or override the paint with a `Style` (`spinner.fail(style=Style(fg="bright_red"))`). Color is stripped under `--no-color`/`NO_COLOR`; off a terminal the line is still written, so the outcome is recorded in logs and pipes.

Because the finisher is written even when the spinner never appeared (a call shorter than the `delay`, a pipe, a non-terminal), gate it on the `shown` property when you only want it after a spinner the reader actually saw:

```python
with Spinner("Baking bread") as spinner:
    bake()
    if spinner.shown:
        spinner.ok()
```

## Elapsed time

Set `timer=True` to append the running wall-clock time to the spinner, and to any `ok()`/`fail()` line:

```python
with Spinner("Simmering stock", timer=True) as spinner:
    sleep(5)
    spinner.ok()  # ✓ Simmering stock (5.0s)
```

The default format is compact: `2.3s`, then `1:05`, then `1:02:03`. For anything else, pass a callable instead of `True` — it receives the elapsed seconds and returns the string to show:

```python
with Spinner("Simmering stock", timer=lambda s: f"{s / 60:.0f} min") as spinner:
    sleep(5)
    spinner.ok()  # ✓ Simmering stock (0 min)
```

Read the elapsed time any moment from the `elapsed_time` property, which freezes once the spinner stops.

## The `--progress` option

`click_extra.command` and `click_extra.group` add a `--progress`/`--no-progress` flag to every CLI by default. It resolves to a single boolean at `ctx.meta["click_extra.progress"]`, which a command reads to decide whether to start a `Spinner`:

```python
from click_extra import Spinner, command, pass_context
from click_extra.context import PROGRESS


@command
@pass_context
def harvest(ctx):
    """Pick apples, showing a spinner when progress is enabled."""
    with Spinner("Picking apples", enabled=None if ctx.meta[PROGRESS] else False):
        sleep(5)
```

Spinner display is **decoupled from color**. A spinner is an interactivity concern, not a color one: it is driven by cursor-control codes, which the [NO_COLOR standard](https://no-color.org) explicitly does not govern. So `--no-color` and `NO_COLOR` strip the spinner's color but keep it spinning, the same way [cargo](https://doc.rust-lang.org/cargo/reference/config.html), npm, pip, [Rich](https://rich.readthedocs.io/en/latest/console.html), [indicatif](https://github.com/console-rs/indicatif) and [ora](https://github.com/sindresorhus/ora) gate progress on the terminal rather than on color.

The resolved value is `False` only for **non-interactive output** (a pipe, a `TERM=dumb` terminal, or CI: handled by the widget's own check when you pass `enabled=None`) and for **explicit intent** (`--no-progress` or `--accessible`, the latter so a screen reader is never handed a spinning glyph).

## Progress bars

The same `--progress`/`--no-progress` flag also gates Click's *determinate* progress bar. `click_extra.progressbar` is a drop-in for [`click.progressbar`](https://click.palletsprojects.com/en/stable/api/#click.progressbar): it reads the resolved flag and hides the bar when progress is off, so a single `--no-progress` (or `--accessible`) silences both the indeterminate spinner and the determinate bar.

```{click:source}
from click_extra import command, progressbar


@command
def harvest():
    """Pick apples behind a determinate progress bar."""
    with progressbar((1, 2, 3), label="Picking apples") as bar:
        for _ in bar:
            pass
```

```{click:run}
# Shown by default: off a TTY the bar emits its label once.
result = invoke(harvest, args=[])
assert result.exit_code == 0
assert "Picking apples" in result.output
```

```{click:run}
# --no-progress hides the bar entirely, exactly as it stops the spinner.
result = invoke(harvest, args=["--no-progress"])
assert result.exit_code == 0
assert "Picking apples" not in result.output
```

The `hidden` argument stays authoritative: pass an explicit `hidden=True` or `hidden=False` to force the bar regardless of the flag, mirroring how an explicit `color=` overrides `ctx.color` on `click.echo`. Color is handled upstream too, since Click renders the bar through `click.echo`: `--no-color` and `NO_COLOR` strip its ANSI without any extra wiring.

## `click_extra.spinner` API

```{eval-rst}
.. autoclasstree:: click_extra.spinner
   :strict:

.. automodule:: click_extra.spinner
   :members:
   :undoc-members:
   :show-inheritance:
```
