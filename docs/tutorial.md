# Tutorial

This tutorial details how we transformed the [canonical `click` example](https://github.com/pallets/click#a-simple-example):

![click CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-help-screen.png)

Into this:

![click-extra CLI help screen](https://github.com/kdeldycke/click-extra/raw/main/docs/images/click-extra-screen.png)

## All bells and whistles

The [canonical `click` example](https://github.com/pallets/click#a-simple-example) is implemented that way:

```python
from click import command, echo, option

@command()
@option("--count", default=1, help="Number of greetings.")
@option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        echo(f"Hello, {name}!")


if __name__ == "__main__":
    hello()
```

To augment the simple example above with all the bells and whistles `click-extra` has in store, all you need is to replace the base command decorators with their `_extra` variants:

```python
from click_extra import command_extra, echo, option

@command_extra()
@option("--count", default=1, help="Number of greetings.")
@option("--name", prompt="Your name", help="The person to greet.")
def hello(count, name):
    """Simple program that greets NAME for a total of COUNT times."""
    for _ in range(count):
        echo(f"Hello, {name}!")


if __name__ == "__main__":
    hello()
```

That's it!
