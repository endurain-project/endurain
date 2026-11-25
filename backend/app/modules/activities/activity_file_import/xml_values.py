"""Read the values of an XML activity file (GPX, TCX) as the decoders store them.

A value that is missing or not usable reads as ``None``, so one bad field never becomes a zero or fails the file.
"""

from datetime import UTC, datetime
from math import isfinite


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
