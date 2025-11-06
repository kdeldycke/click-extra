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

import click
import pytest

from click_extra import (
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
    ("enum_definition", "expected_choices"),
    (
        # String-based Enum.
        (
            Enum("Status", {"PENDING": "pending", "APPROVED": "approved"}),
            ("Status.PENDING", "Status.APPROVED"),
        ),
        # Integer-based Enum.
        (
            Enum("Color", {"RED": 1, "GREEN": 2, "BLUE": 3}),
            ("Color.RED", "Color.GREEN", "Color.BLUE"),
        ),
        # Auto-numbered Enum.
        (
            Enum("Permission", {"READ": auto(), "WRITE": auto(), "EXECUTE": auto()}),
            ("Permission.READ", "Permission.WRITE", "Permission.EXECUTE"),
        ),
        # IntEnum.
        (
            IntEnum("Priority", {"LOW": auto(), "MEDIUM": auto(), "HIGH": auto()}),
            ("1", "2", "3")
            if sys.version_info >= (3, 11)
            else ("Priority.LOW", "Priority.MEDIUM", "Priority.HIGH"),
        ),
        # Difference between Enum and StrEnum: StrEnum defines __str__() to return
        # the value.
        (
            Enum(
                "MyEnum", {"FIRST_VALUE": "first_value", "SECOND_VALUE": "second-value"}
            ),
            ("MyEnum.FIRST_VALUE", "MyEnum.SECOND_VALUE"),
        ),
        (
            StrEnum(
                "MyEnum",
                {"FIRST_VALUE": "first_value", "SECOND_VALUE": "second-value"},
            ),
            ("first_value", "second-value"),
        ),
        (
            StrEnum("MyEnum", {"FIRST_VALUE": auto(), "SECOND_VALUE": auto()}),
            ("first_value", "second_value"),
        ),
        # Flag enums.
        (
            Flag("Features", {"FEATURE_A": auto(), "FEATURE_B": auto()}),
            ("Features.FEATURE_A", "Features.FEATURE_B"),
        ),
        # IntFlag enums.
        (
            IntFlag(
                "Options", {"OPTION_X": auto(), "OPTION_Y": auto(), "OPTION_Z": auto()}
            ),
            ("1", "2", "4")
            if sys.version_info >= (3, 11)
            else ("Options.OPTION_X", "Options.OPTION_Y", "Options.OPTION_Z"),
        ),
    ),
)
def test_enum_default_string_choices(enum_definition, expected_choices) -> None:
    enum_choice = EnumChoice(enum_definition)

    assert enum_choice.choices == expected_choices


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


def test_enum_choice_non_string() -> None:
    class BadEnum(IntEnum):
        FIRST = auto()
        SECOND = auto()

    with pytest.raises(TypeError) as exc_info:
        EnumChoice(BadEnum, choice_source=ChoiceSource.VALUE)

    assert exc_info.value.args[0] == (
        "<BadEnum.FIRST: 1> produced non-string choice 1 when using "
        "<ChoiceSource.VALUE: 'value'>."
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
    ("case_sensitive", "valid_inputs", "invalid_inputs"),
    (
        (
            # Case-insensitive mode.
            False,
            (
                # Choice strings.
                ("my-first-value", MyEnum.FIRST_VALUE),
                ("my-second-value", MyEnum.SECOND_VALUE),
                # Case variations (should be accepted).
                ("MY-FIRST-VALUE", MyEnum.FIRST_VALUE),
                ("My-Second-Value", MyEnum.SECOND_VALUE),
                # Enum members.
                (MyEnum.FIRST_VALUE, MyEnum.FIRST_VALUE),
                (MyEnum.SECOND_VALUE, MyEnum.SECOND_VALUE),
            ),
            (
                "FIRST_VALUE",
                "first_value",
                "my_second_value",
            ),
        ),
        (
            # Case-sensitive mode.
            True,
            (
                # Choice strings.
                ("my-first-value", MyEnum.FIRST_VALUE),
                ("my-second-value", MyEnum.SECOND_VALUE),
                # Enum members.
                (MyEnum.FIRST_VALUE, MyEnum.FIRST_VALUE),
                (MyEnum.SECOND_VALUE, MyEnum.SECOND_VALUE),
            ),
            (
                "FIRST_VALUE",
                "first_value",
                "my_second_value",
                # Case variations should be rejected.
                "MY-FIRST-VALUE",
                "My-Second-Value",
            ),
        ),
    ),
)
def test_enum_choice_command(
    invoke, cmd_decorator, case_sensitive, valid_inputs, invalid_inputs
) -> None:
    """Test EnumChoice used within an option."""

    @cmd_decorator
    @click.option("--my-enum", type=EnumChoice(MyEnum, case_sensitive=case_sensitive))
    def cli(my_enum: MyEnum) -> None:
        echo(f"my_enum: {my_enum!r}")

    # Test valid input.
    for valid_input, expected_member in valid_inputs:
        result = invoke(cli, ["--my-enum", valid_input])
        assert result.stdout == f"my_enum: {expected_member!r}\n"
        assert not result.stderr
        assert result.exit_code == 0

    # Test invalid inputs.
    for invalid_input in invalid_inputs:
        result = invoke(cli, ["--my-enum", invalid_input])
        assert not result.stdout
        assert (
            "Error: Invalid value for '--my-enum': "
            f"'{invalid_input}' is not one of 'my-first-value', 'my-second-value'."
        ) in result.stderr
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
