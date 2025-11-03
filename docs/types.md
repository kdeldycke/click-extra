# {octicon}`file-binary` Types

A collection of custom Click parameter types for common use-cases.

## `EnumChoice`

`click.Choice` is supporting `Enum`s, but naively: the [`Enum.name` property](https://docs.python.org/3/library/enum.html#enum.Enum.name) of each members is used for choices. It [was designed that way to simplify the implementation](https://github.com/pallets/click/issues/2911#issuecomment-2891534372), because it is the part of `Enum` that is guaranteed to be unique strings.

But this is not always what we want, especially when the `Enum`'s names are not user-friendly (e.g. they contain underscores, uppercase letters, etc.). This custom `EnumChoice` type solve this issue by allowing you to select which part of the `Enum` members to use as choice strings.

### `Click.Choice` limits

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

```{click:example}
:emphasize-lines: 15,17
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
invoke(cli, args=["--format", "TEXT"])
invoke(cli, args=["--format", "HTML"])
invoke(cli, args=["--format", "OTHER_FORMAT"])
```

However, using the `value` fails:

```{click:run}
:emphasize-lines: 5,10,15
invoke(cli, args=["--format", "text"])
invoke(cli, args=["--format", "html"])
invoke(cli, args=["--format", "other-format"])
```

This preference for `Enum.name` is also reflected in the help message:

```{click:run}
:emphasize-lines: 5-6
invoke(cli, args=["--help"])
```

To change this behavior, we need `EnumChoice`.

### Usage

Let's use `click_extra.EnumChoice` instead of `click.Choice`, and we override the `__str__` method of our `Enum`:

```{click:example}
:emphasize-lines: 11-12,18
from enum import Enum

from click_extra import command, option, echo, EnumChoice


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
:emphasize-lines: 5
invoke(cli, args=["--help"])
```

User inputs are now matched against the `str()` representation:

```{click:run}
invoke(cli, args=["--format", "other-format"])
```

And not the `Enum.name`:

```{click:run}
:emphasize-lines: 5
invoke(cli, args=["--format", "OTHER_FORMAT"])
```

By customizing the `__str__` method of the `Enum`, you have full control over how choices are displayed and matched.

### Case-sensitivity

`EnumChoice` is case-insensitive by default, unlike `click.Choice`, so random casing are recognized:

```{click:run}
invoke(cli, args=["--format", "oThER-forMAt"])
```

If you want to restore case-sensitive matching, you can enable it by setting the `case_sensitive` parameter to `True`:

```{click:example}
:emphasize-lines: 18
from enum import Enum

from click_extra import command, option, echo, EnumChoice


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
:emphasize-lines: 5
invoke(cli, args=["--format", "oThER-forMAt"])
```

### Choice source

`EnumChoice` use the `str()` representation of each member by default.

But you can configure it to select which part of the members to use as choice strings, by setting the `choice_source` parameter to one of:

- `ChoiceSource.KEY` or `ChoiceSource.NAME` to use the key (i.e. the [`Enum.name` property](https://docs.python.org/3/library/enum.html#enum.Enum.name)),
- `ChoiceSource.VALUE` to use the [`Enum.value`](https://docs.python.org/3/library/enum.html#enum.Enum.value), or
- `ChoiceSource.STR` to use the [`str()` string representation](https://docs.python.org/3/library/enum.html#enum.Enum.__str__) (which is the default behavior).

Here is an example using `ChoiceSource.KEY`:

```{code-block} pycon
:emphasize-lines: 3,6,14
>>> from click_extra import EnumChoice, ChoiceSource

>>> choice_type = EnumChoice(Format, choice_source=ChoiceSource.KEY)

>>> choice_type
EnumChoice('TEXT', 'HTML', 'OTHER_FORMAT')

>>> choice_type.convert("OTHER_FORMAT", None, None)
<Format.OTHER_FORMAT: 'other-format'>

>>> choice_type.convert("other-format", None, None)
Traceback (most recent call last):
  ...
click.exceptions.BadParameter: 'other-format' is not one of 'TEXT', 'HTML', 'OTHER_FORMAT'.
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

### Default value

Unfortunately Click is [hard-coded to use the `Enum.name` in help messages](https://github.com/pallets/click/pull/3004) for the default value. Therefore, even when using `EnumChoice`, the default value will still be displayed using the `name`, which may not match the choice strings:

```{click:example}
:emphasize-lines: 20
from enum import Enum

from click_extra import command, option, echo, EnumChoice


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
    default=Format.HTML,
    show_default=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

```{click:run}
:emphasize-lines: 6
invoke(cli, args=["--help"])
```

One way to work around this limitation is to set the default value to the corresponding choice string:

```{click:example}
:emphasize-lines: 20
from enum import Enum

from click_extra import command, option, echo, EnumChoice


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
    default=Format.HTML.value,
    show_default=True,
    help="Select format.",
)
def cli(format):
    echo(f"Selected format: {format!r}")
```

```{click:run}
:emphasize-lines: 6
invoke(cli, args=["--help"])
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
