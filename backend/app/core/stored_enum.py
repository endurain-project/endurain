"""String enums whose members map to the integer a database column stores.

The API speaks the string; the database keeps its integers. Declaring the pair once on the member means
no second table has to agree with it.
"""

import functools
from enum import StrEnum
from typing import Any, Self


class StoredStrEnum(StrEnum):
    """A string enum whose members each carry the integer stored in the database.

    A member is declared as ``NAME = ("wire_value", stored_int)``. The enum validates only the string, so a
    request that sends the stored integer is refused; :meth:`from_stored` and :meth:`accept_stored` are
    for values read from storage or produced by an internal caller.

    Attributes:
        stored: The integer the database stores for the member.
        label: A human-readable name, the wire value when the member declares none.
    """

    stored: int
    label: str

    def __new__(cls, value: str, stored: int, label: str | None = None) -> Self:
        """Create a member carrying its stored integer.

        Args:
            value: The string the API uses.
            stored: The integer the database stores.
            label: A human-readable name, or None to use ``value``.

        Returns:
            The new member.
        """
        member = str.__new__(cls, value)
        member._value_ = value
        member.stored = stored
        member.label = label if label is not None else value
        return member

    @classmethod
    @functools.cache
    def _by_stored(cls) -> dict[int, Self]:
        """Index the members by their stored integer.

        Returns:
            The members keyed by stored integer.
        """
        return {member.stored: member for member in cls}

    @classmethod
    def from_stored(cls, stored: int) -> Self:
        """Return the member the database stores as ``stored``.

        Args:
            stored: The stored integer.

        Returns:
            The member.

        Raises:
            ValueError: When no member stores ``stored``.
        """
        try:
            return cls._by_stored()[stored]
        except KeyError:
            raise ValueError(f"{stored} is not a stored value of {cls.__name__}") from None

    @classmethod
    def from_value(cls, value: str) -> Self:
        """Return the member a wire value names.

        For a model that validates with ``use_enum_values``, whose fields hold the wire value instead of the
        member, to get the member back.

        Args:
            value: The wire value.

        Returns:
            The member.

        Raises:
            ValueError: When no member has the wire value.
        """
        try:
            return next(member for member in cls if member == value)
        except StopIteration:
            raise ValueError(f"{value!r} is not a value of {cls.__name__}") from None

    @classmethod
    def accept_stored(cls, value: object) -> object:
        """Turn a stored integer into its member and pass anything else through.

        For a ``BeforeValidator`` on a field read from storage or filled by an internal producer, never on
        a field a client writes: there the plain enum refuses the integer.

        Args:
            value: The value being validated.

        Returns:
            The member when ``value`` is an integer, otherwise ``value`` unchanged.
        """
        if isinstance(value, int) and not isinstance(value, bool):
            return cls.from_stored(value)
        return value


def to_stored(values: dict[str, Any]) -> dict[str, Any]:
    """Replace each :class:`StoredStrEnum` member in column values with the integer the database stores.

    Looks inside nested mappings and lists, since a JSON column keeps the stored integers too.

    Args:
        values: Column name to value, as ``model_dump`` returns it.

    Returns:
        A new mapping with every enum member as its stored integer.
    """
    return {field: _stored(value) for field, value in values.items()}


def _stored(value: Any) -> Any:
    """Convert one value, and the values it holds, as :func:`to_stored` does.

    Args:
        value: A column value.

    Returns:
        The value with every enum member replaced.
    """
    if isinstance(value, StoredStrEnum):
        return value.stored
    if isinstance(value, dict):
        return to_stored(value)
    if isinstance(value, list):
        return [_stored(item) for item in value]
    return value
