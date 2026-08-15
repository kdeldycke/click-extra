"""The canonical Click example, verbatim from Click's own readme.

Kept runnable so the "before" screenshot in `readme.md` is regenerated from a
real terminal instead of drawn by hand. Its Click Extra counterpart in
`hello_click_extra.py` holds the same code, down to the line, save for the
import.

See `docs/screenshots.md` for the command that captures both.
"""

import click


@click.command
@click.option("--count", default=1, help="Number of greetings.")
@click.option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        click.echo(f"Hello, {name}!")


if __name__ == "__main__":
    # Click names the program after `sys.argv[0]`, Click Extra after the
    # callback. Pinning it keeps the two screenshots comparable; Click Extra
    # ignores the argument.
    hello(prog_name="hello")
