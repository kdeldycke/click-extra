# {octicon}`file-binary` Types

A collection of custom Click parameter types for common use-cases.

## `EnumChoice`

`click.Choice` is supporting `Enum`s, but naively: the [`Enum.name` property](https://docs.python.org/3/library/enum.html#enum.Enum.name) of each members is used for choices. It [was designed that way to simplify the implementation](https://github.com/pallets/click/issues/2911#issuecomment-2891534372), because it is the part of `Enum` that is guaranteed to be unique strings.

But this is not always what we want, especially when the `Enum`'s names are not user-friendly (e.g. they contain underscores, uppercase letters, etc.). This custom `EnumChoice` type solve this issue by allowing you to select which part of the `Enum` members to use as choice strings.

### Limits of `Click.Choice`

Let's start with a simple example to demonstrate the limitations of `click.Choice`. Starting with this `Format` definition:

```{code-block} python
from enum import Enum

class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"
```

This `Format` gets standard names for each member:

```{code-block} pycon
>>> Format.TEXT.name
'TEXT'

>>> Format.HTML.name
'HTML'

>>> Format.OTHER_FORMAT.name
'OTHER_FORMAT'
```

But we made its values more user-friendly:

```{code-block} pycon
>>> Format.TEXT.value
'text'

>>> Format.HTML.value
'html'

>>> Format.OTHER_FORMAT.value
'other-format'
```

Now let's combine this `Enum` with `click.Choice` into a simple CLI:

```{click:source}
---
emphasize-lines: 15,17
---
from enum import Enum

from click import command, option, echo, Choice


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"


@command
@option(
    "--format",
    type=Choice(Format),
    show_choices=True,
    default=Format.HTML,
    show_default=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

All Enum’s members are properly registered and recognized when using their `name`:

```{click:run}
result = invoke(cli, args=["--format", "TEXT"])
assert result.output == "Selected format: <Format.TEXT: 'text'>\n"
```

```{click:run}
result = invoke(cli, args=["--format", "HTML"])
assert result.output == "Selected format: <Format.HTML: 'html'>\n"
```

```{click:run}
result = invoke(cli, args=["--format", "OTHER_FORMAT"])
assert result.output == "Selected format: <Format.OTHER_FORMAT: 'other-format'>\n"
```

However, using the `value` fails:

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--format", "text"])
assert "'text' is not one of 'TEXT', 'HTML', 'OTHER_FORMAT'." in result.stderr
```

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--format", "html"])
assert "'html' is not one of 'TEXT', 'HTML', 'OTHER_FORMAT'." in result.stderr
```

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--format", "other-format"])
assert "'other-format' is not one of 'TEXT', 'HTML', 'OTHER_FORMAT'." in result.stderr
```

This preference for `Enum.name` is also reflected in the help message, both for choices and default value:

```{click:run}
---
emphasize-lines: 5-6
---
result = invoke(cli, args=["--help"])
assert "--format [TEXT|HTML|OTHER_FORMAT]" in result.stdout
assert "[default: HTML]" in result.stdout
```

To change this behavior, we need `EnumChoice`.

### Usage

Let's use `click_extra.EnumChoice` instead of `click.Choice`, and then override the `__str__` method of our `Enum`:

```{click:source}
---
emphasize-lines: 4,12-13,19
---
from enum import Enum

from click import command, option, echo
from click_extra import EnumChoice


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def __str__(self):
        return self.value


@command
@option(
    "--format",
    type=EnumChoice(Format),
    show_choices=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

This renders into much better help messages:

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--help"])
assert "--format [text|html|other-format]" in result.stdout
```

User inputs are now matched against the `str()` representation:

```{click:run}
result = invoke(cli, args=["--format", "other-format"])
assert result.output == "Selected format: <Format.OTHER_FORMAT: 'other-format'>\n"
```

And not the `Enum.name`:

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--format", "OTHER_FORMAT"])
assert "'OTHER_FORMAT' is not one of 'text', 'html', 'other-format'." in result.stderr
```

By customizing the `__str__` method of the `Enum`, you have full control over how choices are displayed and matched.

### Case-sensitivity

`EnumChoice` is case-insensitive by default, unlike `click.Choice`, so random casing are recognized:

```{click:run}
invoke(cli, args=["--format", "oThER-forMAt"])
```

If you want to restore case-sensitive matching, you can enable it by setting the `case_sensitive` parameter to `True`:

```{click:source}
---
emphasize-lines: 19
---
from enum import Enum

from click import command, option, echo
from click_extra import EnumChoice


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def __str__(self):
        return self.value


@command
@option(
    "--format",
    type=EnumChoice(Format, case_sensitive=True),
    show_choices=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--format", "oThER-forMAt"])
assert "'oThER-forMAt' is not one of 'text', 'html', 'other-format'." in result.stderr
```

### Choice source

`EnumChoice` use the `str()` representation of each member by default. But you can configure it to select which part of the members to use as choice strings.

That's done by setting the `choice_source` parameter to one of:

- `ChoiceSource.KEY` or `ChoiceSource.NAME` to use the key (i.e. the [`Enum.name` property](https://docs.python.org/3/library/enum.html#enum.Enum.name)),
- `ChoiceSource.VALUE` to use the [`Enum.value`](https://docs.python.org/3/library/enum.html#enum.Enum.value), or
- `ChoiceSource.STR` to use the [`str()` string representation](https://docs.python.org/3/library/enum.html#enum.Enum.__str__) (which is the default behavior).

Here is an example using `ChoiceSource.KEY`, which is equivalent to `click.Choice` behavior:

```{click:source}
---
emphasize-lines: 4,19
---
from enum import Enum

from click import command, option, echo
from click_extra import EnumChoice, ChoiceSource


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def __str__(self):
        return self.value


@command
@option(
    "--format",
    type=EnumChoice(Format, choice_source=ChoiceSource.KEY),
    show_choices=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

So even though we still override the `__str__` method, user inputs are now matched against the `name`:

```{click:run}
result = invoke(cli, args=["--format", "OTHER_FORMAT"])
assert result.output == "Selected format: <Format.OTHER_FORMAT: 'other-format'>\n"
```

And not the `str()` representation:

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--format", "other-format"])
assert "'other-format' is not one of 'text', 'html', 'other_format'." in result.stderr
```

Still, as you can see above, the choice strings are [lower-cased, as per `EnumChoice` default](#case-sensitivity). And this is also reflected in the help message:

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--help"])
assert "--format [text|html|other_format]" in result.stdout
```

````{tip}
If you don't want to import `ChoiceSource`, you can also pass the string values `"key"`, `"name"`, `"value"`, or `"str"` to the `choice_source` parameter:

```{code-block} pycon
:emphasize-lines: 1
>>> choice_type = EnumChoice(Format, choice_source="key")

>>> choice_type
EnumChoice('TEXT', 'HTML', 'OTHER_FORMAT')
```
````

### Custom choice source

In addition to the [built-in choice sources](#choice-source) detailed above, you can also provide a custom callable to the `choice_source` parameter. This callable should accept an `Enum` member and return the corresponding string to use as choice.

This is practical when you want to use a specific attribute or method of the `Enum` members as choice strings. Here's an example:

```{click:source}
---
emphasize-lines: 12-13,19
---
from enum import Enum

from click import command, option, echo
from click_extra import EnumChoice


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def display_name(self):
        return f"custom-{self.value}"


@command
@option(
    "--format",
    type=EnumChoice(Format, choice_source=getattr(Format, "display_name")),
    show_choices=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

```{click:run}
---
emphasize-lines: 5
---
result = invoke(cli, args=["--help"])
assert "--format [custom-text|custom-html|custom-other-format]" in result.stdout
```

### Default value

Another limit of `click.Choice` is how the default value is displayed in help messages. Click is [hard-coded to use the `Enum.name` in help messages](https://github.com/pallets/click/pull/3004) for the default value.

To fix this limitation, you have to use `EnumChoice` with `@click_extra.option` or `@click_extra.argument` decorators, which override Click's default help formatter to properly display the default value according to the choice strings.

For example, using `@click_extra.option`:

```{click:source}
---
emphasize-lines: 17,19,21-22
---
from enum import Enum

import click
import click_extra


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def __str__(self):
        return self.value


@click.command
@click_extra.option(
    "--format",
    type=click_extra.EnumChoice(Format),
    show_choices=True,
    default=Format.HTML,
    show_default=True,
    help="Select format.",
)
def cli(format):
    click.echo(f"Selected format: {format!r}")
```

This renders into much better help messages, where the default value is displayed using the choice strings:

```{click:run}
---
emphasize-lines: 6
---
result = invoke(cli, args=["--help"])
assert "--format [text|html|other-format]" in result.stdout
assert "[default: html]" in result.stdout
```

````{warning}
Without Click Extra's `@option` or `@argument`, Click's default help formatter is used, which always displays the default value using the `Enum.name`, even when using `EnumChoice`:

```{click:source}
:emphasize-lines: 17,19
from enum import Enum

import click
import click_extra


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def __str__(self):
        return self.value


@click.command
@click.option(
    "--format",
    type=click_extra.EnumChoice(Format),
    show_choices=True,
    default=Format.HTML,
    show_default=True,
    help="Select format.",
)
def cli(format):
    click.echo(f"Selected format: {format!r}")
```

See the unmatched default value in the help message:

```{click:run}
:emphasize-lines: 6
result = invoke(cli, args=["--help"])
assert "--format [text|html|other-format]" in result.stdout
assert "[default: HTML]" in result.stdout
```

You can still work around this limitation by forcing the default value:

```{click:source}
:emphasize-lines: 21
from enum import Enum

import click
import click_extra


class Format(Enum):
    TEXT = "text"
    HTML = "html"
    OTHER_FORMAT = "other-format"

    def __str__(self):
        return self.value


@click.command
@click.option(
    "--format",
    type=click_extra.EnumChoice(Format),
    show_choices=True,
    default=str(Format.HTML),
    show_default=True,
    help="Select format.",
)
def cli(format):
    click.echo(f"Selected format: {format!r}")
```

```{click:run}
:emphasize-lines: 6
result = invoke(cli, args=["--help"])
assert "--format [text|html|other-format]" in result.stdout
assert "[default: html]" in result.stdout
```
````

### Aliases

`EnumChoice` also supports aliases on both names and values.

Here's an example using aliases:

```{click:source}
---
emphasize-lines: 10,14-15,20,25,30
---
from enum import Enum

from click import command, option, echo
from click_extra import EnumChoice


class State(Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    ONGOING = "in_progress"  # Alias for IN_PROGRESS
    COMPLETED = "completed"

# Dynamiccally add names and values aliases.
State.NEW._add_alias_("fresh")  # Alias for NEW
State.COMPLETED._add_value_alias_("done")  # Alias for COMPLETED

@command
@option(
    "--state",
    type=EnumChoice(State, choice_source="name"),
    show_choices=True,
)
@option(
    "--state-name",
    type=EnumChoice(State, choice_source="name", show_aliases=True),
    show_choices=True,
)
@option(
    "--state-value",
    type=EnumChoice(State, choice_source="value", show_aliases=True),
    show_choices=True,
)
def cli(state, state_name, state_value):
    echo(f"Selected state:       {state!r}")
    echo(f"Selected state-name:  {state_name!r}")
    echo(f"Selected state-value: {state_value!r}")
```

You can now see the name aliases `ongoing` and `fresh` are now featured in the help message if `show_aliases=True`, as well as the value alias `done`:

```{click:run}
---
emphasize-lines: 6-7
---
result = invoke(cli, args=["--help"])
assert "--state [new|in_progress|completed]" in result.stdout
assert "--state-name [new|in_progress|ongoing|completed|fresh]" in result.stdout
assert "--state-value [new|in_progress|completed|done]" in result.stdout
```

And both names and values aliases are properly recognized, and normalized to their corresponding canonocal `Enum` members:

```{click:run}
result = invoke(cli, args=["--state", "in_progress", "--state-name", "ongoing", "--state-value", "done"])
assert result.output == (
    "Selected state:       <State.IN_PROGRESS: 'in_progress'>\n"
    "Selected state-name:  <State.IN_PROGRESS: 'in_progress'>\n"
    "Selected state-value: <State.COMPLETED: 'completed'>\n"
)
```

## `click_extra.types` API

```{eval-rst}
.. autoclasstree:: click_extra.types
   :strict:
```

```{eval-rst}
.. automodule:: click_extra.types
   :members:
   :undoc-members:
   :show-inheritance:
```
