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

## Spin direction

Pass `reverse=True` to rotate the other way. It works with the default frames or any custom sequence:

```python
with Spinner("Chilling lemonade", reverse=True):
    sleep(5)
```

The animation source is just a sequence of strings. `click_extra.spinner` ships the default Braille `SPINNER_FRAMES` and a plain `ASCII_SPINNER_FRAMES` for terminals without Unicode glyphs; pass your own to `frames` for anything else.

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

## `click_extra.spinner` API

```{eval-rst}
.. autoclasstree:: click_extra.spinner
   :strict:

.. automodule:: click_extra.spinner
   :members:
   :undoc-members:
   :show-inheritance:
```
