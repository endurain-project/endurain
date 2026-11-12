"""Annotated types for values a client sends, shared by the request schemas and routes."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BeforeValidator, Field, StrictInt, StrictStr, ValidationInfo

#: The largest value of a PostgreSQL ``integer`` column, which every id column is.
INT32_MAX = 2**31 - 1

#: An id a request body references. Strict, positive and inside the column's range, so a value
#: the database cannot store is a validation failure rather than a 500.
RecordId = Annotated[StrictInt, Field(ge=1, le=INT32_MAX)]

#: Keyset sentinels below and above every id. PostgreSQL compares ``uuid`` bytewise and SQLAlchemy's ``Uuid`` on SQLite
#: stores 32 hex characters, so both orders equal the integer order.
NIL_UUID = uuid.UUID(int=0)
MAX_UUID = uuid.UUID(int=(1 << 128) - 1)

#: The earliest date a record may carry.
_EARLIEST = datetime(1900, 1, 1)


def _not_out_of_range_date(value: date) -> date:
    """Reject a date before 1900 or later than tomorrow in UTC.

    A local date is never more than one day ahead of UTC, so tomorrow in UTC admits every real
    "today" and refuses a typo.

    Args:
        value: The submitted date.

    Returns:
        The date, unchanged.

    Raises:
        ValueError: When the date is outside the range.
    """
    if value < _EARLIEST.date() or value > datetime.now(UTC).date() + timedelta(days=1):
        raise ValueError("Date must be between 1900-01-01 and tomorrow")
    return value


def _not_out_of_range_datetime(value: datetime) -> datetime:
    """Reject a datetime before 1900 or more than a day ahead of now.

    A datetime with an offset is compared in UTC; a naive one is compared as given.

    Args:
        value: The submitted datetime.

    Returns:
        The datetime, unchanged.

    Raises:
        ValueError: When the datetime is outside the range.
    """
    now = datetime.now(UTC)
    if value.tzinfo is None:
        earliest, latest = _EARLIEST, now.replace(tzinfo=None) + timedelta(days=1)
    else:
        earliest, latest = _EARLIEST.replace(tzinfo=UTC), now + timedelta(days=1)
    if value < earliest or value > latest:
        raise ValueError("Date must be between 1900-01-01 and tomorrow")
    return value


#: A calendar date of a record (birthdate, a day's measurement).
RecordDate = Annotated[date, AfterValidator(_not_out_of_range_date)]


def _read_naive_as_utc(value: datetime) -> datetime:
    """Attach UTC to a datetime without an offset.

    Args:
        value: A datetime a provider or an old archive wrote.

    Returns:
        The datetime with an offset; one that already had an offset is unchanged.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


#: An instant of a record a client sends: it carries a UTC offset, which a request without one is refused for.
RecordInstant = Annotated[AwareDatetime, AfterValidator(_not_out_of_range_datetime)]

#: An instant the server writes itself (a provider sync, a profile archive), whose source may omit the offset and
#: means UTC.
ImportedInstant = Annotated[datetime, AfterValidator(_read_naive_as_utc), AfterValidator(_not_out_of_range_datetime)]

#: A wall-clock reading of a record that is deliberately local (a ``*_local`` field): no zone is attached, so the
#: value is kept as sent.
RecordLocalDateTime = Annotated[datetime, AfterValidator(_not_out_of_range_datetime)]


def _stored_decimal_as_text(value: object) -> object:
    """Write a ``Decimal`` a database row holds as the text of a money amount.

    A request carries JSON, which has no ``Decimal``, so only a stored value or an internal producer is converted;
    a JSON number stays a number and is refused by the string type.

    Args:
        value: The submitted or stored amount.

    Returns:
        The amount with two decimals when it was a ``Decimal``, otherwise the value unchanged.
    """
    return f"{value:.2f}" if isinstance(value, Decimal) else value


#: A price in the owner's currency (the ``currency`` user setting) as a decimal string with two decimals, such as
#: ``"129.90"``, up to the 999999999.99 a ``Numeric(11, 2)`` column holds.
Money = Annotated[StrictStr, BeforeValidator(_stored_decimal_as_text), Field(pattern=r"^\d{1,9}\.\d{2}$")]

#: A sum of prices as a decimal string with two decimals, which can pass what one price can be.
MoneyTotal = Annotated[StrictStr, BeforeValidator(_stored_decimal_as_text), Field(pattern=r"^\d+\.\d{2}$")]


def money_from_archived_number(value: object) -> object:
    """Read a price an archive written before prices were decimal strings, a JSON number, as a money amount.

    Args:
        value: The archived price.

    Returns:
        The amount as text with two decimals when it was a number, otherwise the value unchanged.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return value
    return f"{Decimal(str(value)):.2f}"


#: Characters that reorder or hide text around a name: the bidirectional marks and embeddings, the isolates, the
#: word joiner and the byte-order mark. The zero-width joiners U+200C and U+200D stay allowed: Persian, Urdu,
#: Indic scripts and emoji sequences need them.
DIRECTION_CONTROLS = frozenset("\u200e\u200f\u061c\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u2060\ufeff")

#: Validation context key that marks data already stored, which a write re-applies without re-checking.
STORED_CONTEXT = "stored"


def strip_direction_controls(value: str) -> str:
    """Remove the direction controls from a text.

    Args:
        value: The text, such as a name an identity provider sent.

    Returns:
        The text without any character of ``DIRECTION_CONTROLS``.
    """
    return "".join(char for char in value if char not in DIRECTION_CONTROLS)


def _plain_name(value: str, info: ValidationInfo) -> str:
    """Reject a name that is only whitespace or carries a direction control.

    The value is never trimmed. Data re-applied from storage (validation context ``stored``) is passed through, so
    a name saved before this check cannot make an unrelated update fail.

    Args:
        value: The submitted name.
        info: Pydantic's validation info, whose context may mark stored data.

    Returns:
        The name, unchanged.

    Raises:
        ValueError: When the name is blank or holds a direction control.
    """
    if info.context and info.context.get(STORED_CONTEXT):
        return value
    if not value.strip():
        raise ValueError("Name must not be blank")
    if any(char in DIRECTION_CONTROLS for char in value):
        raise ValueError("Name must not contain text direction control characters")
    return value


#: A name a client sends for a person, activity or similar: 1 to 250 characters, not blank, with no direction control characters.
DisplayName = Annotated[StrictStr, Field(min_length=1, max_length=250), AfterValidator(_plain_name)]
