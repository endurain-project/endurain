"""Read and write the values of an XML activity file (GPX, TCX).

On read, a value that is missing or not usable reads as ``None``, so one bad field never becomes a zero or fails the
file. On write, a value is written so the decoders read it back unchanged.
"""

import re
from datetime import UTC, datetime
from decimal import Decimal
from math import isfinite
from xml.sax.saxutils import escape

#: The ranges Garmin's GPX and TCX extension schemas hold: heart rate is 1 to 255 bpm, cadence at most 254 and power
#: and counts an ``unsignedShort``.
_MAX_HEART_RATE = 255
_MAX_CADENCE = 254
_MAX_UNSIGNED_SHORT = 65_535

#: Characters XML 1.0 cannot hold, even escaped.
_NOT_XML = re.compile("[^\t\n\r\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")


def local_name(tag: str) -> str:
    """Return an element tag without its namespace.

    Args:
        tag: The tag as ElementTree gives it, in Clark notation or plain.

    Returns:
        The local name, case kept.
    """
    return tag.rpartition("}")[2]


def finite_number(text: str | None) -> float | None:
    """Read a finite number.

    Args:
        text: The raw text.

    Returns:
        The number, or ``None`` when the text is missing, not a number, NaN or infinite.
    """
    if text is None:
        return None
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if isfinite(value) else None


def non_negative(value: float | None) -> float | None:
    """Return a value unless it is negative.

    Args:
        value: The value, or ``None``.

    Returns:
        The value, or ``None`` when it is ``None`` or negative.
    """
    return value if value is not None and value >= 0 else None


def whole(value: float | None) -> int | None:
    """Round a non-negative value to a whole number.

    Args:
        value: The value, or ``None``.

    Returns:
        The rounded value, or ``None`` when it is ``None`` or negative.
    """
    kept = non_negative(value)
    return None if kept is None else round(kept)


def utc_time(text: str | None) -> datetime | None:
    """Read an ISO 8601 date and time as timezone-aware UTC; a time with no zone is read as UTC.

    Args:
        text: The raw text.

    Returns:
        The time with its sub-second part, or ``None`` when it is missing, a date without a time of day, or not a
        time.
    """
    if text is None or "T" not in text.upper():
        return None
    try:
        # RFC 3339 allows a lowercase "t" separator and "z" zone; fromisoformat reads only uppercase.
        moment = datetime.fromisoformat(text.strip().upper())
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def position(lat_text: str | None, lon_text: str | None) -> tuple[float | None, float | None]:
    """Read a latitude and longitude pair in degrees.

    Args:
        lat_text: The raw latitude.
        lon_text: The raw longitude.

    Returns:
        The pair, or ``(None, None)`` when either is unusable or out of range.
    """
    lat = finite_number(lat_text)
    lon = finite_number(lon_text)
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, None
    return lat, lon


def xml_text(value: str) -> str:
    """Write text as XML element content.

    Args:
        value: The text.

    Returns:
        The text escaped, without the characters XML 1.0 cannot hold.
    """
    return escape(_NOT_XML.sub("", value))


def xml_number(value: float) -> str:
    """Write a finite number in plain decimal notation, which every XML number type accepts.

    Args:
        value: The number.

    Returns:
        The number with no exponent; a float with the shortest digits that read back as the same float.
    """
    if isinstance(value, int):
        return str(value)
    return format(Decimal(repr(value)), "f")


def xml_time(moment: datetime) -> str:
    """Write a time as RFC 3339 UTC with a ``Z`` zone.

    Args:
        moment: A timezone-aware time.

    Returns:
        The time to the second, or to the millisecond or microsecond when it has a sub-second part.
    """
    utc = moment.astimezone(UTC).replace(tzinfo=None)
    if not utc.microsecond:
        timespec = "seconds"
    elif utc.microsecond % 1000:
        timespec = "microseconds"
    else:
        timespec = "milliseconds"
    return utc.isoformat(timespec=timespec) + "Z"


def xml_heart_rate(value: int | None) -> int | None:
    """Return a heart rate the GPX and TCX schemas hold.

    Args:
        value: The heart rate in beats per minute.

    Returns:
        The heart rate, or ``None`` when it is missing or outside 1 to 255.
    """
    return value if value is not None and 1 <= value <= _MAX_HEART_RATE else None


def xml_cadence(value: float | None) -> int | None:
    """Return a cadence as the whole number the GPX and TCX schemas hold.

    Args:
        value: The cadence.

    Returns:
        The rounded cadence, or ``None`` when it is missing, negative or above 254.
    """
    if value is None or not 0 <= round(value) <= _MAX_CADENCE:
        return None
    return round(value)


def xml_unsigned_short(value: int | None) -> int | None:
    """Return a count or power the GPX and TCX schemas hold as an ``unsignedShort``.

    Args:
        value: The value.

    Returns:
        The value, or ``None`` when it is missing or outside 0 to 65,535.
    """
    return value if value is not None and 0 <= value <= _MAX_UNSIGNED_SHORT else None
