# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.

from __future__ import annotations

import importlib.metadata
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import Enum, Flag, IntEnum, IntFlag, auto
from operator import attrgetter

import click
import pytest
from click.testing import CliRunner

from click_extra import (
    UNSET,
    BadParameter,
    Choice,
    ChoiceSource,
    Duration,
    EnumChoice,
    MultiChoice,
    echo,
)
from click_extra.pytest import command_decorators, option_decorators

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum  # type: ignore[import-not-found]


def test_click_choice_behavior() -> None:
    """Lockdown the behavior of method inherited from Click's Choice type."""

    class SimpleEnum(Enum):
        FIRST_VALUE = auto()
        SECOND_VALUE = "second-value"

    enum_choice = Choice(SimpleEnum)

    assert repr(enum_choice) == (
        "Choice([<SimpleEnum.FIRST_VALUE: 1>, "
        "<SimpleEnum.SECOND_VALUE: 'second-value'>])"
    )
    assert enum_choice.choices == (SimpleEnum.FIRST_VALUE, SimpleEnum.SECOND_VALUE)
    assert enum_choice.case_sensitive is True

    # Choice strings or Eunum members are recognized as valid inputs.
    assert enum_choice.convert("FIRST_VALUE", None, None) == SimpleEnum.FIRST_VALUE
    assert enum_choice.convert("SECOND_VALUE", None, None) == SimpleEnum.SECOND_VALUE
    assert enum_choice.convert(SimpleEnum.FIRST_VALUE, None, None) == (
        SimpleEnum.FIRST_VALUE
    )
    assert enum_choice.convert(SimpleEnum.SECOND_VALUE, None, None) == (
        SimpleEnum.SECOND_VALUE
    )

    # Values are not recognized as valid inputs.
    with pytest.raises(BadParameter) as exc_info:
        enum_choice.convert("second-value", None, None)
    assert exc_info.value.args[0] == (
        "'second-value' is not one of 'FIRST_VALUE', 'SECOND_VALUE'."
    )

    # Normalization works for both choice strings and Enum members.
    assert enum_choice.normalize_choice("FIRST_VALUE", None) == "FIRST_VALUE"
    assert enum_choice.normalize_choice("SECOND_VALUE", None) == "SECOND_VALUE"
    assert enum_choice.normalize_choice(SimpleEnum.FIRST_VALUE, None) == "FIRST_VALUE"
    assert enum_choice.normalize_choice(SimpleEnum.SECOND_VALUE, None) == "SECOND_VALUE"

    # Normalization leave stings unchanged (case-sensitive).
    assert enum_choice.normalize_choice("first_value", None) == "first_value"
    assert enum_choice.normalize_choice("Second_Value", None) == "Second_Value"

    # Test case-insensitive behavior.
    enum_choice_ci = Choice(SimpleEnum, case_sensitive=False)
    assert enum_choice_ci.convert("first_value", None, None) == SimpleEnum.FIRST_VALUE
    assert enum_choice_ci.convert("SECOND_value", None, None) == (
        SimpleEnum.SECOND_VALUE
    )
    assert enum_choice_ci.normalize_choice("first_value", None) == "first_value"
    assert enum_choice_ci.normalize_choice("SECOND_value", None) == "second_value"


@pytest.mark.parametrize(
    ("enum_definition", "choice_source", "result"),
    (
        # String-based Enum.
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.STR,
            ("Status.PENDING", "Status.APPROVED"),
        ),
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.NAME,
            ("PENDING", "APPROVED"),
        ),
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.VALUE,
            ("pending", "approved"),
        ),
        # Aliases in string-based Enum are hidden by default.
        (
            Enum(
                "State",
                {
                    "NEW": "new",
                    "IN_PROGRESS": "in_progress",
                    "ONGOING": "in_progress",  # Alias for IN_PROGRESS
                    "COMPLETED": "completed",
                },
            ),
            ChoiceSource.STR,
            ("State.NEW", "State.IN_PROGRESS", "State.COMPLETED"),
        ),
        (
            Enum(
                "State",
                {
                    "NEW": "new",
                    "IN_PROGRESS": "in_progress",
                    "ONGOING": "in_progress",  # Alias for IN_PROGRESS
                    "COMPLETED": "completed",
                },
            ),
            ChoiceSource.NAME,
            ("NEW", "IN_PROGRESS", "COMPLETED"),
        ),
        (
            Enum(
                "State",
                {
                    "NEW": "new",
                    "IN_PROGRESS": "in_progress",
                    "ONGOING": "in_progress",  # Alias for IN_PROGRESS
                    "COMPLETED": "completed",
                },
            ),
            ChoiceSource.VALUE,
            ("new", "in_progress", "completed"),
        ),
        # Integer-based Enum.
        (
            Enum("Color", {"RED": 1, "GREEN": 2, "BLUE": 3}),
            ChoiceSource.STR,
            ("Color.RED", "Color.GREEN", "Color.BLUE"),
        ),
        (
            Enum("Color", {"RED": 1, "GREEN": 2, "BLUE": 3}),
            ChoiceSource.NAME,
            ("RED", "GREEN", "BLUE"),
        ),
        (
            Enum("Color", {"RED": 1, "GREEN": 2, "BLUE": 3}),
            ChoiceSource.VALUE,
            "<Color.RED: 1> produced non-string choice 1",
        ),
        # Aliases in integer-based Enum are hidden by default.
        (
            Enum(
                "Level",
                {
                    "LOW": 1,
                    "MEDIUM": 2,
                    "NORMAL": 2,  # Alias for MEDIUM
                    "HIGH": 3,
                },
            ),
            ChoiceSource.STR,
            ("Level.LOW", "Level.MEDIUM", "Level.HIGH"),
        ),
        (
            Enum(
                "Level",
                {
                    "LOW": 1,
                    "MEDIUM": 2,
                    "NORMAL": 2,  # Alias for MEDIUM
                    "HIGH": 3,
                },
            ),
            ChoiceSource.NAME,
            ("LOW", "MEDIUM", "HIGH"),
        ),
        (
            Enum(
                "Level",
                {
                    "LOW": 1,
                    "MEDIUM": 2,
                    "NORMAL": 2,  # Alias for MEDIUM
                    "HIGH": 3,
                },
            ),
            ChoiceSource.VALUE,
            "<Level.LOW: 1> produced non-string choice 1",
        ),
        # Auto-numbered Enum.
        (
            Enum("Permission", {"READ": auto(), "WRITE": auto(), "EXECUTE": auto()}),
            ChoiceSource.STR,
            ("Permission.READ", "Permission.WRITE", "Permission.EXECUTE"),
        ),
        (
            Enum("Permission", {"READ": auto(), "WRITE": auto(), "EXECUTE": auto()}),
            ChoiceSource.NAME,
            ("READ", "WRITE", "EXECUTE"),
        ),
        (
            Enum("Permission", {"READ": auto(), "WRITE": auto(), "EXECUTE": auto()}),
            ChoiceSource.VALUE,
            "<Permission.READ: 1> produced non-string choice 1",
        ),
        # IntEnum.
        (
            IntEnum("Priority", {"LOW": auto(), "MEDIUM": auto(), "HIGH": auto()}),
            ChoiceSource.STR,
            ("1", "2", "3")
            if sys.version_info >= (3, 11)
            else ("Priority.LOW", "Priority.MEDIUM", "Priority.HIGH"),
        ),
        (
            IntEnum("Priority", {"LOW": auto(), "MEDIUM": auto(), "HIGH": auto()}),
            ChoiceSource.NAME,
            ("LOW", "MEDIUM", "HIGH"),
        ),
        (
            IntEnum("Priority", {"LOW": auto(), "MEDIUM": auto(), "HIGH": auto()}),
            ChoiceSource.VALUE,
            "<Priority.LOW: 1> produced non-string choice 1",
        ),
        # Difference between Enum and StrEnum: StrEnum defines __str__() to return
        # the value.
        (
            Enum(
                "MyEnum", {"FIRST_VALUE": "first_value", "SECOND_VALUE": "second-value"}
            ),
            ChoiceSource.STR,
            ("MyEnum.FIRST_VALUE", "MyEnum.SECOND_VALUE"),
        ),
        (
            StrEnum(
                "MyEnum",
                {"FIRST_VALUE": "first_value", "SECOND_VALUE": "second-value"},
            ),
            ChoiceSource.STR,
            ("first_value", "second-value"),
        ),
        (
            StrEnum("MyEnum", {"FIRST_VALUE": auto(), "SECOND_VALUE": auto()}),
            ChoiceSource.STR,
            ("first_value", "second_value"),
        ),
        (
            StrEnum("MyEnum", {"FIRST_VALUE": auto(), "SECOND_VALUE": auto()}),
            ChoiceSource.NAME,
            ("FIRST_VALUE", "SECOND_VALUE"),
        ),
        (
            StrEnum("MyEnum", {"FIRST_VALUE": auto(), "SECOND_VALUE": auto()}),
            ChoiceSource.VALUE,
            ("first_value", "second_value"),
        ),
        # Flag enums.
        (
            Flag("Features", {"FEATURE_A": auto(), "FEATURE_B": auto()}),
            ChoiceSource.STR,
            ("Features.FEATURE_A", "Features.FEATURE_B"),
        ),
        (
            Flag("Features", {"FEATURE_A": auto(), "FEATURE_B": auto()}),
            ChoiceSource.NAME,
            ("FEATURE_A", "FEATURE_B"),
        ),
        (
            Flag("Features", {"FEATURE_A": auto(), "FEATURE_B": auto()}),
            ChoiceSource.VALUE,
            "<Features.FEATURE_A: 1> produced non-string choice 1",
        ),
        # IntFlag enums.
        (
            IntFlag(
                "Options", {"OPTION_X": auto(), "OPTION_Y": auto(), "OPTION_Z": auto()}
            ),
            ChoiceSource.STR,
            ("1", "2", "4")
            if sys.version_info >= (3, 11)
            else ("Options.OPTION_X", "Options.OPTION_Y", "Options.OPTION_Z"),
        ),
        (
            IntFlag(
                "Options", {"OPTION_X": auto(), "OPTION_Y": auto(), "OPTION_Z": auto()}
            ),
            ChoiceSource.NAME,
            ("OPTION_X", "OPTION_Y", "OPTION_Z"),
        ),
        (
            IntFlag(
                "Options", {"OPTION_X": auto(), "OPTION_Y": auto(), "OPTION_Z": auto()}
            ),
            ChoiceSource.VALUE,
            "<Options.OPTION_X: 1> produced non-string choice 1",
        ),
    ),
)
def test_enum_string_choices(
    enum_definition: type[Enum],
    choice_source: ChoiceSource,
    result: tuple[str, ...] | str,
) -> None:

    # Expecting an error message.
    if isinstance(result, str):
        with pytest.raises(TypeError) as exc_info:
            EnumChoice(enum_definition, choice_source=choice_source)

        assert exc_info.value.args[0] == f"{result} when using {choice_source!r}."
        return

    # Normal case: valid string choices.
    enum_choice = EnumChoice(enum_definition, choice_source=choice_source)

    assert enum_choice.choices == result
    assert len(enum_choice.choices) == len(set(enum_choice.choices))

    for choice_str, member in zip(enum_choice.choices, list(enum_definition)):
        # Conversion from choice strings to Enum members.
        assert enum_choice.convert(choice_str, None, None) == member

        # Conversion from Enum members should be idempotent.
        assert enum_choice.convert(member, None, None) == member


@pytest.mark.skipif(
    sys.version_info < (3, 11), reason="Enum aliasing not supported in Python < 3.11"
)
@pytest.mark.parametrize(
    ("enum_definition", "choice_source", "show_aliases", "result"),
    (
        # String-based Enum.
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.STR,
            False,
            ("Status.PENDING", "Status.APPROVED"),
        ),
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.STR,
            True,
            RuntimeError,
        ),
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.NAME,
            True,
            ("PENDING", "APPROVED", "aliased_pending"),
        ),
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ChoiceSource.VALUE,
            True,
            ("pending", "approved", "aliased_approved"),
        ),
        # Integer-based Enum.
        (
            Enum("Color", {"RED": 1, "GREEN": 2, "BLUE": 3}),
            ChoiceSource.NAME,
            True,
            ("RED", "GREEN", "BLUE", "aliased_pending"),
        ),
        (
            Enum("Color", {"RED": 1, "GREEN": 2, "BLUE": 3}),
            ChoiceSource.VALUE,
            True,
            TypeError,
        ),
    ),
)
@pytest.mark.skipif(
    sys.version_info < (3, 13),
    reason="Enum._add_alias_ and _add_value_alias_ are Python 3.13+ only.",
)
def test_enum_choice_show_aliases(
    enum_definition: type[Enum],
    choice_source: ChoiceSource,
    show_aliases: bool,
    result: type[RuntimeError | TypeError] | tuple[str, ...],
) -> None:
    """Test that EnumChoice correctly handles Enum with aliases."""

    if result is RuntimeError:
        with pytest.raises(RuntimeError) as exc_info:
            EnumChoice(
                enum_definition, choice_source=choice_source, show_aliases=show_aliases
            )

        assert exc_info.value.args[0] == (
            f"Cannot use {choice_source!r} with show_aliases=True."
        )
        return

    elif result is TypeError:
        with pytest.raises(TypeError) as type_exc_info:
            EnumChoice(
                enum_definition, choice_source=choice_source, show_aliases=show_aliases
            )

        assert "produced non-string choice" in type_exc_info.value.args[0]
        assert f"when using {choice_source!r}." in type_exc_info.value.args[0]
        return

    # Augment the Enum with both key/name and value aliases.
    next(iter(enum_definition))._add_alias_("aliased_pending")  # type: ignore[attr-defined]
    list(enum_definition)[1]._add_value_alias_("aliased_approved")  # type: ignore[attr-defined]

    enum_choice = EnumChoice(
        enum_definition, choice_source=choice_source, show_aliases=show_aliases
    )
    assert enum_choice.choices == result
    assert len(enum_choice.choices) == len(set(enum_choice.choices))

    # Map choice strings to Enum members, including aliases.
    choice_to_member = list(zip(enum_choice.choices, list(enum_definition)))
    if isinstance(result, tuple) and "aliased_pending" in result:
        choice_to_member.append(("aliased_pending", next(iter(enum_definition))))
    if isinstance(result, tuple) and "aliased_approved" in result:
        choice_to_member.append(("aliased_approved", list(enum_definition)[1]))

    for choice_str, member in choice_to_member:
        # Conversion from choice strings to Enum members.
        assert enum_choice.convert(choice_str, None, None) == member

        # Conversion from Enum members should be idempotent.
        assert enum_choice.convert(member, None, None) == member


class MyEnum(Enum):
    """Produce different strings for keys/names, values and str()."""

    FIRST_VALUE = "first-value"
    SECOND_VALUE = "second-value"

    def __str__(self) -> str:
        return f"my-{self.value}"


@pytest.mark.parametrize(
    "source, expected_choices",
    (
        # Exact ChoiceSource enum values.
        (ChoiceSource.KEY, ("FIRST_VALUE", "SECOND_VALUE")),
        (ChoiceSource.NAME, ("FIRST_VALUE", "SECOND_VALUE")),
        (ChoiceSource.VALUE, ("first-value", "second-value")),
        (ChoiceSource.STR, ("my-first-value", "my-second-value")),
        # String versions of the ChoiceSource values are supported too.
        ("key", ("FIRST_VALUE", "SECOND_VALUE")),
        ("name", ("FIRST_VALUE", "SECOND_VALUE")),
        ("value", ("first-value", "second-value")),
        ("str", ("my-first-value", "my-second-value")),
        # Random casing are supported too.
        ("kEy", ("FIRST_VALUE", "SECOND_VALUE")),
        ("Name", ("FIRST_VALUE", "SECOND_VALUE")),
        ("valuE", ("first-value", "second-value")),
        ("STR", ("my-first-value", "my-second-value")),
        # Callable choice_source.
        (
            lambda member: f"custom-{member.value}",
            ("custom-first-value", "custom-second-value"),
        ),
        (attrgetter("name"), ("FIRST_VALUE", "SECOND_VALUE")),
    ),
)
def test_enum_choice_internals(
    source: ChoiceSource | str | Callable[[Enum], str],
    expected_choices: tuple[str, ...],
) -> None:
    enum_choice = EnumChoice(MyEnum, choice_source=source)

    # Check the produced choice strings.
    assert enum_choice.choices == expected_choices
    assert len(enum_choice.choices) == 2

    assert repr(enum_choice) == (
        f"EnumChoice('{expected_choices[0]}', '{expected_choices[1]}')"
    )

    # Check internal metadata.
    assert enum_choice.case_sensitive is False
    assert enum_choice._enum is MyEnum
    assert enum_choice._choice_source in ChoiceSource.__members__.values() or callable(
        enum_choice._choice_source
    )
    assert len(enum_choice._enum_map) == 2
    assert tuple(enum_choice._enum_map.keys()) == enum_choice.choices
    assert tuple(enum_choice._enum_map.values()) == tuple(MyEnum)

    # Choice strings and Enum members are normalized correctly
    # (lower-cased by default).
    assert (
        enum_choice.normalize_choice(expected_choices[0], None)
        == expected_choices[0].casefold()
    )
    assert (
        enum_choice.normalize_choice(expected_choices[1], None)
        == expected_choices[1].casefold()
    )
    assert (
        enum_choice.normalize_choice(MyEnum.FIRST_VALUE, None)
        == expected_choices[0].casefold()
    )
    assert (
        enum_choice.normalize_choice(MyEnum.SECOND_VALUE, None)
        == expected_choices[1].casefold()
    )

    # Conversion from choice strings to Enum members.
    assert enum_choice.convert(expected_choices[0], None, None) == MyEnum.FIRST_VALUE
    assert enum_choice.convert(expected_choices[1], None, None) == MyEnum.SECOND_VALUE

    # Conversion from Enum members should be idempotent.
    assert enum_choice.convert(MyEnum.FIRST_VALUE, None, None) == MyEnum.FIRST_VALUE
    assert enum_choice.convert(MyEnum.SECOND_VALUE, None, None) == MyEnum.SECOND_VALUE


@pytest.mark.parametrize("case_sensitive", (True, False, None))
def test_enum_choice_case_sensitivity(case_sensitive: bool) -> None:
    kwargs = {}
    if case_sensitive is not None:
        kwargs["case_sensitive"] = case_sensitive

    enum_choice = EnumChoice(MyEnum, choice_source=ChoiceSource.VALUE, **kwargs)

    assert enum_choice.choices == ("first-value", "second-value")

    # Provide the exact casing.
    assert enum_choice.convert("first-value", None, None) == MyEnum.FIRST_VALUE
    assert enum_choice.convert("second-value", None, None) == MyEnum.SECOND_VALUE

    # Different casing are accepted if case_sensitive is False or not set.
    if not case_sensitive:
        assert enum_choice.convert("FIRST-VALUE", None, None) == MyEnum.FIRST_VALUE
        assert enum_choice.convert("SeCoNd-VaLuE", None, None) == MyEnum.SECOND_VALUE

    # Strict casing is required if case_sensitive is True.
    else:
        with pytest.raises(BadParameter) as exc_info:
            enum_choice.convert("SeCoNd-VaLuE", None, None)
        assert exc_info.value.args[0] == (
            "'SeCoNd-VaLuE' is not one of 'first-value', 'second-value'."
        )


@pytest.mark.parametrize(
    "source, expected",
    (
        (ChoiceSource.KEY, ("first_value", "second_value")),
        (ChoiceSource.VALUE, ("first-value", "second-value")),
        (ChoiceSource.STR, ("my-first-value", "my-second-value")),
    ),
)
@pytest.mark.skipif(
    tuple(int(p) for p in importlib.metadata.version("click").split(".")[:2]) < (8, 4),
    reason="EnumChoice completion is case-folded via Choice.normalize_choice(), added "
    "in Click 8.4 (pallets/click#3471); Click 8.3 returns the raw enum keys.",
)
def test_enum_choice_shell_complete(
    source: ChoiceSource,
    expected: tuple[str, str],
) -> None:
    """Completion offers normalized choice strings, never the ``Enum.member`` form.

    Regression guard for pallets/click#3015, fixed upstream in pallets/click#3471:
    completion routes through ``Choice.normalize_choice()``, so an ``EnumChoice``
    suggests parseable strings (case-folded, as it is case-insensitive by default)
    instead of ``MyEnum.FIRST_VALUE``.
    """
    enum_choice = EnumChoice(MyEnum, choice_source=source)

    # A bare Context/Parameter is enough to drive completion.
    cli = click.Command("cli", params=[click.Option(["--fmt"], type=enum_choice)])
    ctx = click.Context(cli)
    param = cli.params[0]

    def complete(incomplete: str) -> list[str]:
        items = enum_choice.shell_complete(ctx, param, incomplete)
        return [item.value for item in items]

    all_choices = complete("")

    # Empty input lists every normalized choice, in declaration order.
    assert all_choices == list(expected)

    # No suggestion leaks the ``Enum.member`` representation.
    assert not any("MyEnum" in choice for choice in all_choices)

    # Every suggestion parses back to its member.
    for choice in all_choices:
        assert isinstance(enum_choice.convert(choice, param, ctx), MyEnum)

    # Prefix filtering stays case-insensitive.
    second = expected[1]
    assert complete(second) == [second]
    assert complete(second.upper()) == [second]


def test_enum_choice_duplicate_string() -> None:
    class BadEnum(StrEnum):
        FIRST = auto()
        SECOND = auto()

        def __str__(self) -> str:
            return "constant-str"

    with pytest.raises(ValueError) as exc_info:
        EnumChoice(BadEnum, choice_source=ChoiceSource.STR)

    assert exc_info.value.args[0] == (
        "<enum 'BadEnum'> has duplicated choice string 'constant-str' for members "
        "<BadEnum.FIRST: 'first'> and <BadEnum.SECOND: 'second'> when using "
        "<ChoiceSource.STR: 'str'>."
    )


@pytest.mark.parametrize(
    # XXX Got a strange issue with double <Option my_enum> in the cli()
    # with the click_extra.command(), hence the no_extra=True parameter here.
    "cmd_decorator",
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize(
    "opt_decorator", option_decorators(no_arguments=True, with_parenthesis=False)
)
@pytest.mark.parametrize(
    ("case_sensitive", "valid_args", "invalid_args"),
    (
        (
            # Case-insensitive mode.
            False,
            (
                # Exact choice strings.
                (["--my-enum", "my-first-value"], MyEnum.FIRST_VALUE),
                (["--my-enum", "my-second-value"], MyEnum.SECOND_VALUE),
                (["--my-enum", str(MyEnum.FIRST_VALUE)], MyEnum.FIRST_VALUE),
                (["--my-enum", str(MyEnum.SECOND_VALUE)], MyEnum.SECOND_VALUE),
                # Case variations are accepted.
                (["--my-enum", "MY-FIRST-VALUE"], MyEnum.FIRST_VALUE),
                (["--my-enum", "My-Second-Value"], MyEnum.SECOND_VALUE),
                # Enum members.
                (["--my-enum", MyEnum.FIRST_VALUE], MyEnum.FIRST_VALUE),
                (["--my-enum", MyEnum.SECOND_VALUE], MyEnum.SECOND_VALUE),
                # Empty input defaults to None.
                ([], None),
            ),
            (
                ["--my-enum", "FIRST_VALUE"],
                ["--my-enum", "first_value"],
                ["--my-enum", "my_second_value"],
                ["--my-enum", MyEnum.FIRST_VALUE.name],
                ["--my-enum", MyEnum.FIRST_VALUE.value],
                # Garbage types.
                ["--my-enum", 123],
                ["--my-enum", 45.67],
                ["--my-enum", True],
                ["--my-enum", False],
                # Missing and blank values.
                ["--my-enum"],
                ["--my-enum", None],
                ["--my-enum", ""],
                ["--my-enum", UNSET],
            ),
        ),
        (
            # Case-sensitive mode.
            True,
            (
                # Exact choice strings.
                (["--my-enum", "my-first-value"], MyEnum.FIRST_VALUE),
                (["--my-enum", "my-second-value"], MyEnum.SECOND_VALUE),
                (["--my-enum", str(MyEnum.FIRST_VALUE)], MyEnum.FIRST_VALUE),
                (["--my-enum", str(MyEnum.SECOND_VALUE)], MyEnum.SECOND_VALUE),
                # Enum members.
                (["--my-enum", MyEnum.FIRST_VALUE], MyEnum.FIRST_VALUE),
                (["--my-enum", MyEnum.SECOND_VALUE], MyEnum.SECOND_VALUE),
                # Empty input defaults to None.
                ([], None),
            ),
            (
                ["--my-enum", "FIRST_VALUE"],
                ["--my-enum", "first_value"],
                ["--my-enum", "my_second_value"],
                ["--my-enum", MyEnum.FIRST_VALUE.name],
                ["--my-enum", MyEnum.FIRST_VALUE.value],
                # Case variations are rejected.
                ["--my-enum", "MY-FIRST-VALUE"],
                ["--my-enum", "My-Second-Value"],
                # Garbage types.
                ["--my-enum", 123],
                ["--my-enum", 45.67],
                ["--my-enum", True],
                ["--my-enum", False],
                # Missing and blank values.
                ["--my-enum"],
                ["--my-enum", None],
                ["--my-enum", ""],
                ["--my-enum", UNSET],
            ),
        ),
    ),
)
def test_enum_choice_command(
    invoke, cmd_decorator, opt_decorator, case_sensitive, valid_args, invalid_args
) -> None:
    """Test EnumChoice used within an option."""

    @cmd_decorator
    @opt_decorator("--my-enum", type=EnumChoice(MyEnum, case_sensitive=case_sensitive))
    def cli(my_enum: MyEnum) -> None:
        echo(f"my_enum: {my_enum!r}")

    # Test valid input.
    for args, expected_member in valid_args:
        result = invoke(cli, args)
        assert result.stdout == f"my_enum: {expected_member!r}\n"
        assert not result.stderr
        assert result.exit_code == 0

    # Test invalid inputs.
    for args in invalid_args:
        result = invoke(cli, args)
        assert not result.stdout
        if len(args) == 2 and args[1] is not None:
            # Invalid value provided.
            msg = (
                "Error: Invalid value for '--my-enum': "
                f"'{args[1]}' is not one of 'my-first-value', 'my-second-value'."
            )
        else:
            # Missing value.
            msg = "Error: Option '--my-enum' requires an argument."
        assert msg in result.stderr
        assert result.exit_code == 2

    # Test help message.
    result = invoke(cli, ["--help"], color=False)
    assert "--my-enum [my-first-value|my-second-value]" in result.stdout
    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
@pytest.mark.parametrize(
    ("opt_decorator", "opt_type"),
    option_decorators(no_arguments=True, with_parenthesis=False, with_types=True),
)
@pytest.mark.parametrize(
    "default_value", (MyEnum.SECOND_VALUE, str(MyEnum.SECOND_VALUE), "my-second-value")
)
def test_enum_choice_default_value(
    invoke, cmd_decorator, opt_decorator, opt_type, default_value
) -> None:
    """Test EnumChoice used within an option with a default value."""

    @cmd_decorator
    @opt_decorator(
        "--my-enum", type=EnumChoice(MyEnum), default=default_value, show_default=True
    )
    def cli(my_enum: MyEnum) -> None:
        echo(f"my_enum: {my_enum!r}")

    # Test default value is used when option is not provided.
    result = invoke(cli)
    assert result.stdout == "my_enum: <MyEnum.SECOND_VALUE: 'second-value'>\n"
    assert not result.stderr
    assert result.exit_code == 0

    # Test help message showing the default.
    result = invoke(cli, ["--help"], color=False)
    assert "--my-enum [my-first-value|my-second-value]" in result.stdout

    # @click_extra.command fix the rendering of Enum default, but not the other
    # vanilla decorators.
    if "extra" not in opt_type and isinstance(default_value, MyEnum):
        default_rendering = "SECOND_VALUE"
    else:
        default_rendering = default_value
    assert f"[default: {default_rendering}]" in result.stdout

    assert not result.stderr
    assert result.exit_code == 0


@pytest.mark.parametrize("cmd_decorator", command_decorators(no_groups=True))
@pytest.mark.parametrize(
    "opt_decorator",
    option_decorators(no_arguments=True, with_parenthesis=False),
)
@pytest.mark.parametrize(
    ("default_value", "expected"),
    (
        # A single-member default, the member given three equivalent ways.
        ((MyEnum.SECOND_VALUE,), (MyEnum.SECOND_VALUE,)),
        ((str(MyEnum.SECOND_VALUE),), (MyEnum.SECOND_VALUE,)),
        (("my-second-value",), (MyEnum.SECOND_VALUE,)),
        # Several members define a multi-column priority order.
        (
            (MyEnum.FIRST_VALUE, MyEnum.SECOND_VALUE),
            (MyEnum.FIRST_VALUE, MyEnum.SECOND_VALUE),
        ),
        # An empty default stays empty.
        ((), ()),
    ),
)
def test_enum_choice_multiple_default_value(
    invoke, cmd_decorator, opt_decorator, default_value, expected
) -> None:
    """A ``multiple=True`` EnumChoice resolves each member of its tuple default.

    Regression test for the ``get_default()`` override stringifying the whole
    default tuple (``str((MyEnum.FOO,))``) instead of mapping each member, which
    made the default trip Click's ``Value must be an iterable`` check.
    """

    @cmd_decorator
    @opt_decorator(
        "--my-enum",
        type=EnumChoice(MyEnum),
        multiple=True,
        default=default_value,
    )
    def cli(my_enum: tuple[MyEnum, ...]) -> None:
        echo(f"my_enum: {my_enum!r}")

    # The default path (option omitted) must resolve to the member tuple.
    result = invoke(cli)
    assert result.exit_code == 0
    assert result.stdout == f"my_enum: {expected!r}\n"
    assert not result.stderr


@pytest.mark.parametrize(
    # XXX Reuse the same no_extra=True workaround as test_enum_choice_command and
    # test_enum_choice_callback: click_extra.command() re-decorates the command,
    # producing a second nargs=-1 parameter that Click's parser rejects with
    # "Cannot have two nargs < 0".
    "cmd_decorator",
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize(
    "opt_decorator",
    option_decorators(no_options=True, with_parenthesis=False),
)
@pytest.mark.parametrize(
    ("default_value", "expected"),
    (
        # A single-member default, the member given two equivalent ways. Unlike the
        # multiple=True option above, a raw value-string default ("my-second-value")
        # is not exercised here: Click re-validates an argument's default through
        # EnumChoice.convert(), which only accepts the choice strings, not the
        # underlying Enum values.
        ((MyEnum.SECOND_VALUE,), (MyEnum.SECOND_VALUE,)),
        ((str(MyEnum.SECOND_VALUE),), (MyEnum.SECOND_VALUE,)),
        # Several members preserve their order.
        (
            (MyEnum.FIRST_VALUE, MyEnum.SECOND_VALUE),
            (MyEnum.FIRST_VALUE, MyEnum.SECOND_VALUE),
        ),
        # An empty default stays empty.
        ((), ()),
    ),
)
def test_enum_choice_variadic_default_value(
    invoke, cmd_decorator, opt_decorator, default_value, expected
) -> None:
    """A variadic (nargs=-1) EnumChoice argument resolves each member of its default.

    Companion to test_enum_choice_multiple_default_value covering the other branch
    of the get_default() override: the nargs == -1 path taken by arguments rather
    than the multiple path taken by options. Both map get_choice_string() over the
    members of a tuple default instead of stringifying the whole tuple.
    """

    @cmd_decorator
    @opt_decorator(
        "my_enum",
        type=EnumChoice(MyEnum),
        nargs=-1,
        default=default_value,
    )
    def cli(my_enum: tuple[MyEnum, ...]) -> None:
        echo(f"my_enum: {my_enum!r}")

    # The default path (no argument supplied) must resolve to the member tuple.
    result = invoke(cli)
    assert result.exit_code == 0
    assert result.stdout == f"my_enum: {expected!r}\n"
    assert not result.stderr


@pytest.mark.parametrize(
    # XXX Reuse the same no_extra=True workaround as test_enum_choice_command to
    # avoid the double <Option my_enum> issue with click_extra.command().
    "cmd_decorator",
    command_decorators(no_groups=True, no_extra=True),
)
@pytest.mark.parametrize(
    "opt_decorator",
    option_decorators(no_arguments=True, with_parenthesis=False),
)
@pytest.mark.parametrize(
    ("choice_source", "cli_value"),
    (
        (ChoiceSource.STR, "my-first-value"),
        (ChoiceSource.VALUE, "first-value"),
        (ChoiceSource.KEY, "FIRST_VALUE"),
    ),
)
def test_enum_choice_callback(
    invoke, cmd_decorator, opt_decorator, choice_source, cli_value
) -> None:
    """Test that option callbacks receive properly converted Enum members."""
    callback_received: list[MyEnum] = []

    def my_callback(ctx, param, value):
        """Callback that checks it receives an Enum member, not a string."""
        if value is not None:
            callback_received.append(value)
        return value

    @cmd_decorator
    @opt_decorator(
        "--my-enum",
        type=EnumChoice(MyEnum, choice_source=choice_source),
        callback=my_callback,
    )
    def cli(my_enum: MyEnum) -> None:
        echo(f"my_enum: {my_enum!r}")

    result = invoke(cli, ["--my-enum", cli_value])
    assert result.exit_code == 0
    assert result.stdout == f"my_enum: {MyEnum.FIRST_VALUE!r}\n"
    assert not result.stderr
    assert len(callback_received) >= 1
    assert all(isinstance(v, MyEnum) for v in callback_received)
    assert all(v is MyEnum.FIRST_VALUE for v in callback_received)


# --- MultiChoice ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("a", ("a",)),
        ("a,b,c", ("a", "b", "c")),
        ("a, b ,c", ("a", "b", "c")),  # Whitespace around tokens is stripped.
        ("a,,b,", ("a", "b")),  # Empty tokens (trailing comma, doubles) dropped.
        ("", ()),
        (None, ()),
        (("a", "b"), ("a", "b")),  # Tuple defaults flow through unchanged.
        (["a", "b"], ("a", "b")),  # Same for lists.
    ),
)
def test_multi_choice_parses_input(raw, expected) -> None:
    """``convert()`` splits on the separator, strips whitespace, drops empties."""
    t = MultiChoice()  # No ``choices``: no validation, just parsing.
    assert t.convert(raw, None, None) == expected


def test_multi_choice_validates_against_choices() -> None:
    """Unknown tokens raise ``BadParameter`` via ``self.fail()``."""
    t = MultiChoice(choices=("a", "b", "c"))
    assert t.convert("a,b", None, None) == ("a", "b")
    with pytest.raises(BadParameter, match=r"Unknown value\(s\): 'd', 'e'"):
        t.convert("a,d,e", None, None)


def test_multi_choice_case_insensitive_normalizes() -> None:
    """``case_sensitive=False`` matches case-insensitively and returns the canonical case."""
    t = MultiChoice(choices=("Alpha", "Beta"), case_sensitive=False)
    assert t.convert("ALPHA,beta", None, None) == ("Alpha", "Beta")
    with pytest.raises(BadParameter, match=r"Unknown value\(s\): 'gamma'"):
        t.convert("alpha,gamma", None, None)


@pytest.mark.parametrize(
    ("choices", "separator", "expected"),
    (
        ((), ",", None),  # No choices: fall back to the default ``MULTI`` metavar.
        (("a", "b", "c"), ",", "[a,b,c]"),
        (("x", "y"), ":", "[x:y]"),  # Configurable separator drives the metavar.
    ),
)
def test_multi_choice_metavar(choices, separator, expected) -> None:
    t = MultiChoice(choices=choices, separator=separator)
    assert t.get_metavar(None) == expected


def test_multi_choice_in_click_option() -> None:
    """End-to-end: ``MultiChoice`` plugs into a Click option like ``Choice`` does."""
    captured: list[tuple[str, ...]] = []

    @click.command
    @click.option("--tags", type=MultiChoice(("alpha", "beta", "gamma")), default=())
    def cli(tags: tuple[str, ...]) -> None:
        captured.append(tags)

    runner = CliRunner()
    result = runner.invoke(cli, ["--tags", "alpha,gamma"])
    assert result.exit_code == 0
    assert captured == [("alpha", "gamma")]

    # The rendered help carries the comma-separated metavar.
    help_text = runner.invoke(cli, ["--help"]).stdout
    assert "[alpha,beta,gamma]" in help_text

    # An unknown tag fails at parse time, before the callback runs.
    result = runner.invoke(cli, ["--tags", "alpha,delta"])
    assert result.exit_code != 0
    assert "'delta'" in result.stderr


# --- Duration -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        # Friendly durations.
        ("7 days", timedelta(days=7)),
        ("1 week", timedelta(weeks=1)),
        ("2 weeks", timedelta(weeks=2)),
        ("3d", timedelta(days=3)),
        ("12h", timedelta(hours=12)),
        ("30m", timedelta(minutes=30)),
        ("45s", timedelta(seconds=45)),
        ("1.5d", timedelta(days=1, hours=12)),
        # A bare number defaults to days.
        ("7", timedelta(days=7)),
        # Spacing and case are irrelevant.
        ("  6   HOURS  ", timedelta(hours=6)),
        # ISO 8601 durations.
        ("P7D", timedelta(days=7)),
        ("P1W", timedelta(weeks=1)),
        ("PT12H", timedelta(hours=12)),
        ("PT30M", timedelta(minutes=30)),
        ("PT45S", timedelta(seconds=45)),
        ("P1WT6H", timedelta(weeks=1, hours=6)),
        ("P2DT3H30M", timedelta(days=2, hours=3, minutes=30)),
        # ISO 8601 is case-insensitive.
        ("p7d", timedelta(days=7)),
        ("pt12h", timedelta(hours=12)),
        # Zero and empty values parse to None.
        ("0", None),
        ("0 days", None),
        ("PT0H", None),
        ("", None),
        (None, None),
    ),
)
def test_duration_parsing(value, expected) -> None:
    assert Duration().convert(value, None, None) == expected


def test_duration_passthrough_timedelta() -> None:
    """An already-parsed timedelta is returned unchanged (idempotent conversion)."""
    delta = timedelta(days=2)
    assert Duration().convert(delta, None, None) is delta


@pytest.mark.parametrize(
    "value",
    (
        "bogus",
        "2 fortnights",
        "abc",
        "tomorrow",
        "-3d",
        # Bare ISO 8601 prefix with no components.
        "P",
        # Unknown ISO 8601 unit.
        "P3X",
        # Date without a time zone.
        "2024-05-01",
        "2024-05-01T00:00:00",
        # Malformed RFC 3339 timestamp.
        "2024-99-99T00:00:00Z",
    ),
)
def test_duration_invalid(value) -> None:
    with pytest.raises(BadParameter):
        Duration().convert(value, None, None)


@pytest.mark.parametrize(
    "value",
    (
        # Friendly form.
        "7 months",
        "1 year",
        "3 months",
        "2 years",
        # ISO 8601 form (M before T = months, Y = years).
        "P3M",
        "P1Y",
        "P1Y6M",
    ),
)
def test_duration_rejects_calendar_units(value) -> None:
    """Months and years are explicitly rejected because their length is ambiguous."""
    with pytest.raises(BadParameter) as exc_info:
        Duration().convert(value, None, None)
    assert "calendar units" in str(exc_info.value)
    assert "ambiguous" in str(exc_info.value)


@pytest.mark.parametrize(
    "value",
    (
        # Z suffix.
        "2024-05-01T00:00:00Z",
        # Explicit UTC offset.
        "2024-05-01T00:00:00+00:00",
        # Non-UTC offset.
        "2024-05-01T02:00:00+02:00",
        # Lowercase T and Z accepted.
        "2024-05-01t00:00:00z",
    ),
)
def test_duration_absolute_timestamp(value) -> None:
    """An RFC 3339 timestamp is converted to ``now - timestamp`` at parse time."""
    result = Duration().convert(value, None, None)
    expected = datetime.now(tz=timezone.utc) - datetime(2024, 5, 1, tzinfo=timezone.utc)
    assert isinstance(result, timedelta)
    assert abs(result - expected) < timedelta(seconds=5)


def test_duration_future_timestamp_parses_to_none() -> None:
    """A timestamp in the future parses to ``None``, read as "no cutoff"."""
    assert Duration().convert("2999-01-01T00:00:00Z", None, None) is None


def test_duration_in_click_option() -> None:
    """End-to-end: ``Duration`` plugs into a Click option."""
    captured: list[timedelta | None] = []

    @click.command
    @click.option("--max-age", type=Duration())
    def cli(max_age: timedelta | None) -> None:
        captured.append(max_age)

    runner = CliRunner()
    result = runner.invoke(cli, ["--max-age", "1 week"])
    assert result.exit_code == 0
    assert captured == [timedelta(weeks=1)]

    # A zero duration reaches the command as None.
    captured.clear()
    result = runner.invoke(cli, ["--max-age", "0"])
    assert result.exit_code == 0
    assert captured == [None]

    # The rendered help carries the default uppercased metavar.
    help_text = runner.invoke(cli, ["--help"]).stdout
    assert "--max-age DURATION" in help_text

    # An invalid duration fails at parse time, before the callback runs.
    captured.clear()
    result = runner.invoke(cli, ["--max-age", "2 fortnights"])
    assert result.exit_code != 0
    assert "'2 fortnights' is not a valid duration" in result.stderr
    assert not captured
