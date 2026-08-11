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
"""Custom `click.ParamType` subclasses for multi-pick, `Enum` choices and
durations, plus the standalone duration parsers that back `Duration`."""

from __future__ import annotations

import enum
import re
from datetime import datetime, timedelta, timezone

import click
from click.shell_completion import CompletionItem

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any


class MultiChoice(click.ParamType):
    """Comma-separated multi-pick from a fixed set of values.

    The pick-many counterpart to {class}`click.Choice`. Accepts a single token
    containing several values joined by a configurable `separator` (defaults
    to `,`), parses it into a `tuple[str, ...]` and validates each value
    against `choices` when that set is non-empty.

    The rendered metavar is `[a,b,c]` (separator-joined, parallel to
    `Choice`'s `[a|b|c]`): `click_extra.highlight._HelpColorsMixin`
    auto-detects the separator and highlights each individual value the same way
    it does for `Choice`.

    ```{note}
    Click does not ship a built-in equivalent. The closest idiomatic
    approach is `click.Choice([...]) + multiple=True`, which requires the
    flag to be repeated (`--tag a --tag b --tag c`) rather than
    comma-separated. The lack of a single-token, separator-based variant
    upstream has been raised in:

    - [pallets/click#2771](https://github.com/pallets/click/issues/2771)
      (open): request for `nargs=-1` with a non-whitespace separator,
      covering exactly this use case.
    - [pallets/click#2537](https://github.com/pallets/click/issues/2537)
      (closed as not planned): earlier request for space-separated multi
      values via `nargs=-1` on options.

    Maintainers have leaned on the orthogonality argument: `multiple=True`
    already exists, separator conventions vary across communities (`,`
    vs. `:` vs. `;`), and escaping breaks down when a value contains
    the chosen separator. `MultiChoice` ships the convention anyway
    because SQL-style `SELECT a, b, c` syntax reads more naturally for
    the tabular use cases `click-extra` supports
    ({class}`click_extra.table.ColumnsOption` is the headline consumer).
    ```
    """

    name = "multi"

    def __init__(
        self,
        choices: Sequence[str] = (),
        separator: str = ",",
        case_sensitive: bool = True,
    ) -> None:
        """Initialize the type.

        :param choices: the accepted values. When non-empty, `convert()`
            rejects unknown tokens with `fail`. When empty, the type
            behaves as a pure separator-aware parser and leaves validation to
            the consumer.
        :param separator: the token boundary. Use any single character; this
            also drives the metavar rendering (`[a<sep>b<sep>c]`).
        :param case_sensitive: when `False`, tokens match `choices`
            case-insensitively and the returned tuple holds the canonical
            (original-case) values from `choices`.
        """
        self.choices: tuple[str, ...] = tuple(choices)
        self.separator: str = separator
        self.case_sensitive: bool = case_sensitive

    def get_metavar(self, param, ctx=None):
        """Render `[a<sep>b<sep>c]` when `choices` is set, `None` otherwise.

        `None` falls back to Click's default rendering (the uppercased
        `name`, like `MULTI`).
        """
        if self.choices:
            return "[" + self.separator.join(self.choices) + "]"
        return None

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> tuple[str, ...]:
        """Split `value` on `separator` and validate each token.

        Already-parsed tuples and lists are returned unchanged so defaults
        declared as tuples flow through untouched. Empty tokens (consecutive
        separators, trailing separator) are dropped silently.
        """
        if value is None:
            return ()
        if isinstance(value, (tuple, list)):
            return tuple(value)
        tokens = tuple(t.strip() for t in str(value).split(self.separator) if t.strip())

        if not self.choices:
            return tokens

        if self.case_sensitive:
            valid = set(self.choices)
            unknown = [t for t in tokens if t not in valid]
            normalized = tokens
        else:
            lookup = {c.casefold(): c for c in self.choices}
            unknown = [t for t in tokens if t.casefold() not in lookup]
            normalized = tuple(lookup.get(t.casefold(), t) for t in tokens)

        if unknown:
            joined = ", ".join(repr(t) for t in unknown)
            accepted = ", ".join(self.choices)
            self.fail(f"Unknown value(s): {joined}. Accepted: {accepted}.", param, ctx)

        return normalized

    def __repr__(self) -> str:
        return f"MultiChoice({list(self.choices)!r}, separator={self.separator!r})"


class ChoiceSource(enum.Enum):
    """Source of choices for `EnumChoice`."""

    # KEY and NAME are synonyms.
    KEY = "key"
    NAME = "name"
    VALUE = "value"
    STR = "str"


class EnumChoice(click.Choice):
    """Choice type for `Enum`.

    Allows to select which part of the members to use as choice strings, by setting the
    `choice_source` parameter to one of:

    - `ChoiceSource.KEY` or `ChoiceSource.NAME` to use the key (the `name`
      property),
    - `ChoiceSource.VALUE` to use the `value`,
    - `ChoiceSource.STR` to use the `str()` string representation, or
    - A custom callable that takes an `Enum` member and returns a string.

    Defaults to `ChoiceSource.STR`, which only requires you to define the
    `__str__()` method on your `Enum` to produce beautiful choice strings.

    The `transform` parameter takes a callable reshaping the string produced by
    the source. It composes with every source, and is the only way to spell
    choices in a CLI-friendly case while `show_aliases` is on: aliases are
    reachable through `ChoiceSource.KEY`, `ChoiceSource.NAME` and
    `ChoiceSource.VALUE` alone, which are stuck on raw Python identifiers.
    """

    choices: tuple[str, ...]
    """The strings available as choice.

    ```{hint}
    Contrary to the parent `Choice` class, we store choices directly as
    strings, not the `Enum` members themselves. That way there is no surprises
    when displaying them to the user.

    This trick bypass `Enum`-specific code path in the Click library. Because,
    after all, a terminal environment only deals with strings: arguments,
    parameters, parsing, help messages, environment variables, etc.
    ```
    """

    def __init__(
        self,
        choices: type[enum.Enum],
        case_sensitive: bool = False,
        choice_source: ChoiceSource
        | str
        | Callable[[enum.Enum], str] = ChoiceSource.STR,
        show_aliases: bool = False,
        transform: Callable[[str], str] | None = None,
    ) -> None:
        """Same as `click.Choice`, but takes an `Enum` as `choices`.

        Also defaults to case-insensitive matching.
        """

        self._enum: type[enum.Enum]
        """The `Enum` class used for choices."""

        self._enum_map: dict[str, enum.Enum]
        """Mapping of choice strings to `Enum` members."""

        self._choice_source: ChoiceSource | Callable[[enum.Enum], str]
        """The source used to derive choice strings from Enum members."""

        self._show_aliases = show_aliases
        """Whether to show member aliases in help messages.

        ```{attention}
        Only works with `ChoiceSource.KEY`, `ChoiceSource.NAME` and
        `ChoiceSource.VALUE`. See `transform` to reshape the identifiers these
        sources produce.
        ```
        """

        self._transform = transform
        """Callable reshaping the string produced by the choice source.

        Applies to every source, aliases included. Because it runs on the choice
        string and not on the member, it can tell an alias apart from its
        canonical member, which `ChoiceSource.STR` and a callable source cannot.
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
                    f"Cannot use {self._choice_source!r} with show_aliases=True. "
                    "An alias is the very same object as the member it points to, "
                    "so it is only distinguishable as a key of the name and value "
                    "maps: pick ChoiceSource.KEY, NAME or VALUE, and reshape the "
                    "identifiers they produce with the transform argument."
                )

            for choice, member in member_source.items():
                self._check_choice_str(member, choice)
                self._register_choice(
                    self._transform_choice_str(member, choice), member
                )

        # No need to include aliases in the choices: iterate the Enum to let it
        # provide us with the canonical members.
        else:
            for member in self._enum:
                self._register_choice(self.get_choice_string(member), member)

        super().__init__(choices=self._enum_map, case_sensitive=case_sensitive)

    def _check_choice_str(
        self, member: enum.Enum, choice: Any, origin: Any = None
    ) -> None:
        """Check that the derived choice string is indeed a string.

        `origin` names the culprit in the error message, and defaults to the
        choice source.
        """
        if not isinstance(choice, str):
            if origin is None:
                origin = self._choice_source
            raise TypeError(
                f"{member!r} produced non-string choice {choice!r} when using "
                f"{origin!r}."
            )

    def _transform_choice_str(self, member: enum.Enum, choice: str) -> str:
        """Reshape a derived choice string with the `transform` callable, if any."""
        if self._transform is None:
            return choice
        try:
            transformed = self._transform(choice)
        except Exception as ex:
            raise ValueError(
                f"cannot call {self._transform!r} on {choice!r}: {ex}"
            ) from ex
        self._check_choice_str(member, transformed, origin=self._transform)
        return transformed

    def _register_choice(self, choice: str, member: enum.Enum) -> None:
        """Map a choice string to its `Enum` member, rejecting collisions.

        A `transform` collapsing two spellings into one is caught here: dropping
        the loser silently would remove a choice from the help screen without a
        word.
        """
        # Duplicates are still under the responsibility of the user.
        if choice in self._enum_map:
            raise ValueError(
                f"{self._enum} has duplicated choice string {choice!r} for "
                f"members {self._enum_map[choice]!r} and {member!r} when using "
                f"{self._choice_source!r}."
            )
        self._enum_map[choice] = member

    def get_choice_string(self, member: enum.Enum) -> str:
        """Derive the choice string from the given `Enum`'s `member`.

        The string produced by the choice source is passed through `transform`.
        """
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
                    f"cannot call {self._choice_source!r} on {member!r}: {ex}"
                ) from ex

        else:
            raise ValueError(f"Unsupported choice source {self._choice_source!r}.")

        self._check_choice_str(member, choice)
        return self._transform_choice_str(member, choice)

    def normalize_choice(self, choice: object, ctx: click.Context | None) -> str:
        """Expand the parent's `normalize_choice()` to accept `Enum` members as input.

        An `Enum` member is mapped to its choice string first; any other value
        is passed to the parent untouched.
        """
        if isinstance(choice, enum.Enum):
            choice = self.get_choice_string(choice)
        return super().normalize_choice(choice, ctx)

    def shell_complete(
        self,
        ctx: click.Context,
        param: click.Parameter,
        incomplete: str,
    ) -> list[CompletionItem]:
        """Return completion items with choices normalized via `normalize_choice()`.

        Overrides the parent to ensure `normalize_choice()` is always called on
        each candidate, fixing Click 8.4.0 where `shell_complete()` returned raw
        (unnormalized) choice strings for `ChoiceSource.KEY`.

        ```{note}
        On Click 8.4.1+ this override is a no-op: the parent already calls
        `normalize_choice()`, and re-normalizing is idempotent
        (`casefold(casefold(s)) == casefold(s)`).
        ```
        """
        str_choices = [self.normalize_choice(choice, ctx) for choice in self.choices]
        if self.case_sensitive:
            matched = (c for c in str_choices if c.startswith(incomplete))
        else:
            incomplete = incomplete.lower()
            matched = (c for c in str_choices if c.lower().startswith(incomplete))
        return [CompletionItem(c) for c in matched]

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> enum.Enum:
        """Convert the input value to the corresponding `Enum` member.

        The parent's `convert()` is going to return the choice string, which we
        then map back to the corresponding `Enum` member.
        """
        choice_string = super().convert(value, param, ctx)
        return self._enum_map[choice_string]

    def __repr__(self) -> str:
        return f"EnumChoice{self.choices!r}"


_DURATION_UNIT_SECONDS = {
    "": 86400,
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "hour": 3600,
    "hours": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}
"""Number of seconds each recognized friendly unit represents (empty unit means days)."""

_DURATION_CALENDAR_UNITS = frozenset({
    "mo",
    "mon",
    "month",
    "months",
    "y",
    "yr",
    "yrs",
    "year",
    "years",
})
"""Calendar units rejected for ambiguity: months span 28-31 days, years 365-366."""

_DURATION_FRIENDLY_PATTERN = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[a-z]*)")

_DURATION_ISO8601_PATTERN = re.compile(
    r"P"
    r"(?:(?P<years>\d+(?:\.\d+)?)Y)?"
    r"(?:(?P<months>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<weeks>\d+(?:\.\d+)?)W)?"
    r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?",
)

_DURATION_EXAMPLES = (
    "'7 days', '1 week', '12h', '30m', 'P7D', 'PT12H', "
    "or an RFC 3339 timestamp like '2024-05-01T00:00:00Z'"
)

_DURATION_CALENDAR_REJECT = (
    "calendar units (months, years) are rejected because their length is "
    "ambiguous: months span 28-31 days, years 365-366. Use days or weeks "
    "instead, like '30 days' or '4 weeks'."
)


def _parse_friendly(text: str, value: Any) -> timedelta | None:
    """Parse a normalized friendly duration, raising `ValueError` on failure.

    *text* is the stripped, lower-cased input; *value* is the original, quoted
    verbatim in the error message.
    """
    match = _DURATION_FRIENDLY_PATTERN.fullmatch(text)
    if match:
        unit = match["unit"]
        if unit in _DURATION_CALENDAR_UNITS:
            raise ValueError(f"{value!r}: {_DURATION_CALENDAR_REJECT}")
        if unit in _DURATION_UNIT_SECONDS:
            seconds = float(match["value"]) * _DURATION_UNIT_SECONDS[unit]
            return timedelta(seconds=seconds)
    raise ValueError(
        f"{value!r} is not a valid duration (examples: {_DURATION_EXAMPLES})."
    )


def _parse_iso8601(text: str, value: Any) -> timedelta | None:
    """Parse a normalized ISO 8601 duration, raising `ValueError` on failure.

    *text* is the stripped, upper-cased input; *value* is the original, quoted
    verbatim in the error message.
    """
    match = _DURATION_ISO8601_PATTERN.fullmatch(text)
    if not match or not any(match.groups()):
        raise ValueError(
            f"{value!r} is not a valid ISO 8601 duration "
            f"(examples: 'P7D', 'PT12H', 'P1WT6H'). Accepted: {_DURATION_EXAMPLES}."
        )
    groups = match.groupdict()
    if groups["years"] or groups["months"]:
        raise ValueError(f"{value!r}: {_DURATION_CALENDAR_REJECT}")
    seconds = (
        float(groups["weeks"] or 0) * 604800
        + float(groups["days"] or 0) * 86400
        + float(groups["hours"] or 0) * 3600
        + float(groups["minutes"] or 0) * 60
        + float(groups["seconds"] or 0)
    )
    return timedelta(seconds=seconds)


def _parse_timestamp(
    text: str, value: Any, *, now: datetime | None = None
) -> timedelta | None:
    """Parse an RFC 3339 timestamp into its age, raising `ValueError` on failure.

    The age is `reference - timestamp`, where *reference* defaults to the
    current UTC time. A timestamp at or after *reference* yields `None`.
    """
    normalized = text.upper().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(
            f"{value!r} looks like an RFC 3339 timestamp but cannot be "
            f"parsed. Accepted: {_DURATION_EXAMPLES}."
        ) from None
    if ts.tzinfo is None:
        raise ValueError(
            f"{value!r} is missing a time zone. Use a fully qualified "
            "RFC 3339 timestamp with 'Z' or an offset like '+00:00'."
        )
    reference = now if now is not None else datetime.now(tz=timezone.utc)
    delta = reference - ts.astimezone(timezone.utc)
    return delta if delta.total_seconds() > 0 else None


def _parse_duration_strict(
    value: Any, *, now: datetime | None = None
) -> timedelta | None:
    """Dispatch *value* to the matching parser, raising `ValueError` on failure.

    The strict core shared by the {class}`Duration` parameter type, which turns
    the `ValueError` into a Click parameter error, and by the soft
    {func}`parse_duration` family, which swallows it and returns `None`.
    """
    text = str(value).strip()
    if not text:
        return None
    # RFC 3339 absolute timestamp: starts with a 4-digit year and a dash.
    if len(text) >= 5 and text[:4].isdigit() and text[4] == "-":
        return _parse_timestamp(text, value, now=now)
    # ISO 8601 duration: starts with 'P' (case-insensitive).
    if text[:1] in ("P", "p"):
        return _parse_iso8601(text.upper(), value)
    # Friendly duration.
    return _parse_friendly(text.lower(), value)


def parse_duration(value: Any, *, now: datetime | None = None) -> timedelta | None:
    """Parse a friendly, ISO 8601 or RFC 3339 duration into a `timedelta`.

    The soft, library-friendly counterpart of the {class}`Duration` parameter
    type: it accepts the same three input shapes but returns `None` instead of
    raising when *value* matches none of them, so it suits classifying values
    read from files or other machine sources. Unlike `Duration`, it does not
    collapse a zero duration to `None`: `parse_duration("0")` is `timedelta(0)`,
    letting callers tell a zero duration from an unparsable value. `None` is
    returned only for an empty value, a future timestamp, or a value matching no
    known form.

    :param value: The duration to parse. An existing `timedelta` (or `None`) is
        returned unchanged.
    :param now: Reference instant for an RFC 3339 timestamp's age; defaults to
        the current UTC time.
    :return: The parsed {class}`~datetime.timedelta` (possibly zero), or `None`.
    """
    if value is None or isinstance(value, timedelta):
        return value
    try:
        return _parse_duration_strict(value, now=now)
    except ValueError:
        return None


def parse_friendly_duration(value: Any) -> timedelta | None:
    """Parse only a friendly duration (`7 days`, `12h`, a bare number of days).

    Returns the parsed {class}`~datetime.timedelta` (possibly zero, so
    `"0 days"` is `timedelta(0)`), or `None` for anything that is not a friendly
    duration: ISO 8601 forms, calendar units (months, years), and empty or
    unrecognized values. See {func}`parse_duration` for the format-detecting
    umbrella.
    """
    try:
        return _parse_friendly(str(value).strip().lower(), value)
    except ValueError:
        return None


def parse_iso8601_duration(value: Any) -> timedelta | None:
    """Parse only an ISO 8601 duration (`P7D`, `PT12H`, `P1WT6H`).

    Returns the parsed {class}`~datetime.timedelta` (possibly zero, so `"PT0S"`
    is `timedelta(0)`), or `None` for anything that is not an ISO 8601 duration:
    friendly forms, calendar (year or month) components, and empty or
    unrecognized values. See {func}`parse_duration` for the format-detecting
    umbrella.
    """
    try:
        return _parse_iso8601(str(value).strip().upper(), value)
    except ValueError:
        return None


class Duration(click.ParamType):
    """Parse a duration or an age into a {class}`datetime.timedelta`.

    Accepts three input shapes:

    - **Friendly duration**: `7 days`, `1 week`, `12h`, `30m`, `45s`,
      or a bare number of days like `7`. Case-insensitive.
    - **ISO 8601 duration**: `P7D`, `PT12H`, `P1WT6H`. Case-insensitive.
    - **RFC 3339 absolute timestamp**: `2024-05-01T00:00:00Z` or with an
      offset like `+02:00`. Converted at parse time to its age,
      `now - timestamp`.

    Some inputs parse to `None` instead of a `timedelta`: a zero duration,
    an empty string, and a timestamp in the future. Cutoff options (cooldowns,
    timeouts, retention windows, cache TTLs) read `None` as "no cutoff", so
    a `0` on the command line disables the gate and overrides a value set in
    a configuration file.

    To parse outside a Click parameter (classifying a value read from a file,
    say), reach for the soft {func}`parse_duration` family, which returns `None`
    instead of raising on an unrecognized value.

    ```{note}
    Durations resolve to a fixed number of seconds, assuming a day is 24
    hours. The local time zone, DST transitions, and calendar boundaries are
    ignored. Calendar units (months, years) are rejected for the same
    reason: 28-31 days and 365-366 days make them unsuitable for a precise
    cutoff. Use `days` or `weeks` instead.
    ```
    """

    name = "duration"

    def convert(
        self, value: Any, param: click.Parameter | None, ctx: click.Context | None
    ) -> timedelta | None:
        """Coerce `value` to a {class}`datetime.timedelta` (or `None`).

        Delegates to {func}`_parse_duration_strict`, turning its `ValueError`
        into a Click parameter error via {meth}`~click.ParamType.fail`. A parsed
        zero duration collapses to `None`, so `0` disables a cutoff option.
        """
        if value is None or isinstance(value, timedelta):
            return value
        try:
            result = _parse_duration_strict(value)
        except ValueError as exc:
            self.fail(str(exc), param, ctx)
        # A zero duration reads as "no cutoff": `0` disables the gate.
        return result or None
