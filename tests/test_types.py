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

import sys
from collections.abc import Callable
from enum import Enum, Flag, IntEnum, IntFlag, auto
from operator import attrgetter

import pytest

from click_extra import (
    UNSET,
    BadParameter,
    Choice,
    ChoiceSource,
    EnumChoice,
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
    assert enum_choice.normalize_choice("FIRST_VALUE", None) == "FIRST_VALUE"  # type: ignore[arg-type]
    assert enum_choice.normalize_choice("SECOND_VALUE", None) == "SECOND_VALUE"  # type: ignore[arg-type]
    assert enum_choice.normalize_choice(SimpleEnum.FIRST_VALUE, None) == "FIRST_VALUE"
    assert enum_choice.normalize_choice(SimpleEnum.SECOND_VALUE, None) == "SECOND_VALUE"

    # Normalization leave stings unchanged (case-sensitive).
    assert enum_choice.normalize_choice("first_value", None) == "first_value"  # type: ignore[arg-type]
    assert enum_choice.normalize_choice("Second_Value", None) == "Second_Value"  # type: ignore[arg-type]

    # Test case-insensitive behavior.
    enum_choice_ci = Choice(SimpleEnum, case_sensitive=False)
    assert enum_choice_ci.convert("first_value", None, None) == SimpleEnum.FIRST_VALUE
    assert enum_choice_ci.convert("SECOND_value", None, None) == (
        SimpleEnum.SECOND_VALUE
    )
    assert enum_choice_ci.normalize_choice("first_value", None) == "first_value"  # type: ignore[arg-type]
    assert enum_choice_ci.normalize_choice("SECOND_value", None) == "second_value"  # type: ignore[arg-type]


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
            else ("LOW", "MEDIUM", "HIGH"),
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
    enum_definition: Enum, choice_source: ChoiceSource, result: tuple[str, ...] | str
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

    for choice_str, member in zip(enum_choice.choices, enum_definition):
        # Conversion from choice strings to Enum members.
        assert enum_choice.convert(choice_str, None, None) == member

        # Conversion from Enum members should be idempotent.
        assert enum_choice.convert(member, None, None) == member


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
            "<Color.RED: 1> produced non-string choice 1",
        ),
    ),
)
def test_enum_choice_show_aliases(
    enum_definition: Enum,
    choice_source: ChoiceSource,
    show_aliases: bool,
    result: tuple[str, ...] | Exception | str,
) -> None:
    """Test that EnumChoice correctly handles Enum with aliases."""

    if result is RuntimeError:
        with pytest.raises(result) as exc_info:
            EnumChoice(
                enum_definition, choice_source=choice_source, show_aliases=show_aliases
            )

        assert exc_info.value.args[0] == (
            f"Cannot use {choice_source!r} with show_aliases=True."
        )
        return

    elif isinstance(result, str):
        with pytest.raises(TypeError) as exc_info:
            EnumChoice(
                enum_definition, choice_source=choice_source, show_aliases=show_aliases
            )

        assert exc_info.value.args[0] == f"{result} when using {choice_source!r}."
        return

    # Augment the Enum with both key/name and value aliases.
    tuple(enum_definition)[0]._add_alias_("aliased_pending")
    tuple(enum_definition)[1]._add_value_alias_("aliased_approved")

    enum_choice = EnumChoice(
        enum_definition, choice_source=choice_source, show_aliases=show_aliases
    )
    assert enum_choice.choices == result
    assert len(enum_choice.choices) == len(set(enum_choice.choices))

    # Map choice strings to Enum members, including aliases.
    choice_to_member = list(zip(enum_choice.choices, enum_definition))
    if "aliased_pending" in result:
        choice_to_member.append(("aliased_pending", tuple(enum_definition)[0]))
    if "aliased_approved" in result:
        choice_to_member.append(("aliased_approved", tuple(enum_definition)[1]))

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

    # Choice strings and Enum members are normalized correctly (i.e.
    # lower-cased by default).
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
