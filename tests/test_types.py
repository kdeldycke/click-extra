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

import enum
import sys
from enum import Enum, IntEnum, auto

import pytest

from click_extra import (
    BadParameter,
    Choice,
    ChoiceSource,
    EnumChoice,
    command,
    echo,
    option,
)

if sys.version_info < (3, 11):
    enum.StrEnum = enum.Enum  # type: ignore[assignment]


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


# TODO: test with all Enum types (IntEnum, Flag, IntFlag, etc.)
def test_simple_enum_choice() -> None:
    """By default, EnumChoice uses ChoiceSource.STR."""

    class SimpleEnum(enum.StrEnum):
        FIRST_VALUE = auto()
        SECOND_VALUE = "second-value"

    enum_choice = EnumChoice(SimpleEnum)

    assert enum_choice.choices == ("first_value", "second-value")
    assert repr(enum_choice) == "EnumChoice('first_value', 'second-value')"


class MyEnum(enum.StrEnum):
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
    ),
)
def test_enum_choice_internals(
    source: ChoiceSource | str, expected_choices: tuple[str, ...]
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
    assert enum_choice._choice_source in ChoiceSource
    assert len(enum_choice._enum_map) == 2
    assert tuple(enum_choice._enum_map.keys()) == enum_choice.choices
    assert tuple(enum_choice._enum_map.values()) == tuple(MyEnum)

    # Choice strings and Enum members are normalized correctly (i.e. lower-cased by default).
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


def test_non_string_choice() -> None:
    class BadEnum(IntEnum):
        FIRST = auto()
        SECOND = auto()

    with pytest.raises(TypeError) as exc_info:
        EnumChoice(BadEnum, choice_source=ChoiceSource.VALUE)

    assert exc_info.value.args[0] == (
        "<BadEnum.FIRST: 1> produced non-string choice 1 when using "
        "<ChoiceSource.VALUE: 'value'>."
    )


def test_duplicate_choice_string() -> None:
    class BadEnum(enum.StrEnum):
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
    invoke, case_sensitive, valid_inputs, invalid_inputs
) -> None:
    """Test EnumChoice used within an option."""

    @command
    @option("--my-enum", type=EnumChoice(MyEnum, case_sensitive=case_sensitive))
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
        assert (
            "Error: Invalid value for '--my-enum': "
            f"'{invalid_input}' is not one of 'my-first-value', 'my-second-value'."
        ) in result.stderr
        assert not result.stdout
        assert result.exit_code == 2

    # Test help message.
    result = invoke(cli, ["--help"])
    assert "--my-enum [my-first-value|my-second-value]" in result.stdout
    assert result.exit_code == 0
