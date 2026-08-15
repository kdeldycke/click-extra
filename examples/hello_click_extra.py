"""The canonical Click example, with Click Extra swapped in for Click.

Nothing changes but the import: the decorators, the options and the callback are
those of `hello_click.py`. Everything the "after" screenshot in `readme.md`
shows beyond that (the colors, and the whole second half of the option list)
comes from Click Extra's defaults.

See `docs/screenshots.md` for the command that captures both.
"""

from click_extra import command, echo, option


@command
@option("--count", default=1, help="Number of greetings.")
@option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        echo(f"Hello, {name}!")


if __name__ == "__main__":
    hello()
