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

from enum import IntEnum, StrEnum, auto

import pytest

from click_extra import BadParameter, ChoiceSource, EnumChoice


# TODO: test with all Enum types (IntEnum, Flag, IntFlag, etc.)
def test_simple_enum_choice() -> None:
    """By default, EnumChoice uses ChoiceSource.STR."""

    class SimpleEnum(StrEnum):
        FIRST_VALUE = auto()
        SECOND_VALUE = "second-value"

    enum_choice = EnumChoice(SimpleEnum)

    assert enum_choice.choices == ("first_value", "second-value")


class MyEnum(StrEnum):
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

    # Check internal metadata.
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
