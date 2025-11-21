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

import click

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any


class ChoiceSource(enum.Enum):
    """Source of choices for ``EnumChoice``."""

    # KEY and NAME are synonyms.
    KEY = "key"
    NAME = "name"
    VALUE = "value"
    STR = "str"


class EnumChoice(click.Choice):
    """Choice type for ``Enum``.

    Allows to select which part of the members to use as choice strings, by setting the
    ``choice_source`` parameter to one of:

    - ``ChoiceSource.KEY`` or ``ChoiceSource.NAME`` to use the key (i.e. the ``name``
      property),
    - ``ChoiceSource.VALUE`` to use the ``value``,
    - ``ChoiceSource.STR`` to use the ``str()`` string representation, or
    - A custom callable that takes an ``Enum`` member and returns a string.

    Default to ``ChoiceSource.STR``, which makes you to only have to define the
    ``__str__()`` method on your ``Enum`` to produce beautiful choice strings.
    """

    choices: tuple[str, ...]
    """The strings available as choice.

    .. hint::
        Contrary to the parent ``Choice`` class, we store choices directly as
        strings, not the ``Enum`` members themselves. That way there is no surprises
        when displaying them to the user.

        This trick bypass ``Enum``-specific code path in the Click library. Because,
        after all, a terminal environment only deals with strings: arguments,
        parameters, parsing, help messages, environment variables, etc.
    """

    def __init__(
        self,
        choices: type[enum.Enum],
        case_sensitive: bool = False,
        choice_source: ChoiceSource
        | str
        | Callable[[enum.Enum], str] = ChoiceSource.STR,
        show_aliases: bool = False,
    ) -> None:
        """Same as ``click.Choice``, but takes an ``Enum`` as ``choices``.

        Also defaults to case-insensitive matching.
        """

        self._enum: type[enum.Enum]
        """The ``Enum`` class used for choices."""

        self._enum_map: dict[str, enum.Enum]
        """Mapping of choice strings to ``Enum`` members."""

        self._choice_source: ChoiceSource | Callable[[enum.Enum], str]
        """The source used to derive choice strings from Enum members."""

        self._show_aliases = show_aliases
        """Whether to show member aliases in help messages.

        .. attention::
            Only works with ``ChoiceSource.KEY``, ``ChoiceSource.NAME`` and
            ``ChoiceSource.VALUE``.
        """

        # Keep the Enum class around.
        assert issubclass(choices, enum.Enum), (
            f"choice_enum must be a subclass of Enum, got {choices!r}."
        )
        self._enum = choices

        # Normalize choice_source to ChoiceSource.
        if isinstance(choice_source, str) and not callable(choice_source):
            self._choice_source = getattr(ChoiceSource, choice_source.upper())
        else:
            self._choice_source = choice_source

        # Build the mapping of choice strings to Enum members.
        self._enum_map = {}

        # Rely on Enum internals to extract all members, including aliases.
        if self._show_aliases:
            if self._choice_source in (ChoiceSource.KEY, ChoiceSource.NAME):
                member_source = self._enum.__members__
            elif self._choice_source == ChoiceSource.VALUE:
                member_source = (
                    self._enum._value2member_map_  # type: ignore[assignment]
                )
            else:
                raise RuntimeError(
                    f"Cannot use {self._choice_source!r} with show_aliases=True."
                )

            for choice, member in member_source.items():
                self._check_choice_str(member, choice)
                self._enum_map[choice] = member

        # No need to include aliases in the choices: iterate the Enum to let it
        # provide us with the canonical members.
        else:
            for member in self._enum:
                choice = self.get_choice_string(member)
                # Duplicates are still under the responsibility of the user.
                if choice in self._enum_map:
                    raise ValueError(
                        f"{self._enum} has duplicated choice string {choice!r} for "
                        f"members {self._enum_map[choice]!r} and {member!r} when using "
                        f"{self._choice_source!r}."
                    )
                self._enum_map[choice] = member

        super().__init__(choices=self._enum_map, case_sensitive=case_sensitive)

    def _check_choice_str(self, member: enum.Enum, choice: Any) -> None:
        """Check that the derived choice string is indeed a string."""
        if not isinstance(choice, str):
            raise TypeError(
                f"{member!r} produced non-string choice {choice!r} when using "
                f"{self._choice_source!r}."
            )

    def get_choice_string(self, member: enum.Enum) -> str:
        """Derivate the choice string from the given ``Enum``'s ``member``."""
        if self._choice_source in (ChoiceSource.KEY, ChoiceSource.NAME):
            choice = member.name

        elif self._choice_source == ChoiceSource.VALUE:
            choice = member.value

        elif self._choice_source == ChoiceSource.STR:
            choice = str(member)

        elif callable(self._choice_source):
            try:
                choice = self._choice_source(member)
            except Exception as ex:
                raise ValueError(
                    f"cannot call {self._choice_source!r} on for {member!r}: {ex}"
                ) from ex

        self._check_choice_str(member, choice)
        return choice

    def normalize_choice(
        self, choice: enum.Enum | str, ctx: click.Context | None
    ) -> str:
        """Expand the parent's ``normalize_choice()`` to accept ``Enum`` members as input.

        Parent method expects a string, but here we allow passing ``Enum`` members too.
        """
        if isinstance(choice, enum.Enum):
            choice = self.get_choice_string(choice)
        return super().normalize_choice(choice, ctx)

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> enum.Enum:
        """Convert the input value to the corresponding ``Enum`` member.

        The parent's ``convert()`` is going to return the choice string, which we
        then map back to the corresponding ``Enum`` member.
        """
        choice_string = super().convert(value, param, ctx)
        return self._enum_map[choice_string]

    def __repr__(self) -> str:
        return f"EnumChoice{self.choices!r}"
