"""The canonical Click example, with Click Extra swapped in for Click.

Holds the same code as `hello_click.py`, down to the line, save for the import:
Click Extra proxies the whole Click namespace, so aliasing it back to `click`
leaves every decorator and call untouched. Everything the "after" screenshot in
`readme.md` shows beyond the two original options comes from Click Extra's
defaults.

See `docs/screenshots.md` for the command that captures both.
"""

import click_extra as click


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
